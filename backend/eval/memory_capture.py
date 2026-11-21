from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings
from app.memory.batch_source_contracts import BatchInput, BatchTurnSource


class CapturedMemorySource(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    campaign_id: UUID
    language: str = Field(min_length=1)
    turns: tuple[BatchTurnSource, ...]

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("language must not be blank")
        return value

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    def source_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


class LegacyTurn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    id: UUID
    turn_number: int
    player_action: str
    narration: str


def ordered_turns(rows: tuple[LegacyTurn, ...]) -> tuple[LegacyTurn, ...]:
    numbers = [row.turn_number for row in rows]
    ids = [row.id for row in rows]
    if len(numbers) != len(set(numbers)):
        raise ValueError(
            "Campaign has duplicate display turn numbers; refusing ambiguous legacy history"
        )
    if len(ids) != len(set(ids)):
        raise ValueError(
            "Campaign has duplicate turn identities; refusing ambiguous legacy history"
        )
    return rows


def partition_capture(
    source: CapturedMemorySource, batch_size: int
) -> tuple[tuple[BatchInput, ...], tuple[BatchTurnSource, ...]]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    complete_count = len(source.turns) // batch_size * batch_size
    complete = source.turns[:complete_count]
    tail = source.turns[complete_count:]

    def batch(turns: tuple[BatchTurnSource, ...]) -> BatchInput:
        rebased = tuple(
            turn.model_copy(update={"reference": f"t{index}"})
            for index, turn in enumerate(turns, 1)
        )
        return BatchInput(turns=rebased)

    batches = tuple(
        batch(complete[index : index + batch_size])
        for index in range(0, len(complete), batch_size)
    )
    return batches, tuple(
        turn.model_copy(update={"reference": f"t{index}"}) for index, turn in enumerate(tail, 1)
    )


async def capture_campaign(session: AsyncSession, campaign_id: UUID) -> CapturedMemorySource:
    connection = await session.connection()
    transaction_settings = (
        await session.execute(
            text(
                "SELECT current_setting('transaction_read_only'), "
                "current_setting('transaction_isolation')"
            )
        )
    ).one()
    if transaction_settings[0] != "on":
        raise RuntimeError("Campaign capture requires a READ ONLY transaction")
    if transaction_settings[1] != "repeatable read":
        raise RuntimeError("Campaign capture requires REPEATABLE READ isolation")
    tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    if "campaigns" not in tables or "turns" not in tables:
        raise RuntimeError("Configured database lacks campaign turn tables")
    columns = await connection.run_sync(
        lambda sync: {
            table: {column["name"] for column in inspect(sync).get_columns(table)}
            for table in ("campaigns", "turns")
        }
    )
    campaign_columns = columns["campaigns"]
    turn_columns = columns["turns"]
    if "language" not in campaign_columns:
        raise RuntimeError("Campaign language is unavailable in this database")

    history_markers = {"active_head_turn_id", "active_continuation_id", "memory_policy_id"}
    if (
        history_markers & campaign_columns
        or {"continuation_id", "parent_turn_id", "history_depth"} & turn_columns
    ):
        raise RuntimeError(
            "History-aware campaign capture is unsupported; use the history-aware batch loader"
        )
    if not {"id", "turn_number", "player_action", "narration", "created_at"} <= turn_columns:
        raise RuntimeError("Legacy turn ordering columns are unavailable")

    campaign = (
        (
            await session.execute(
                text("SELECT id, language, turn_number FROM campaigns WHERE id = :campaign_id"),
                {"campaign_id": campaign_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if campaign is None:
        raise ValueError("Campaign not found")
    result = await session.execute(
        text(
            "SELECT id, turn_number, player_action, narration FROM turns "
            "WHERE campaign_id = :campaign_id ORDER BY turn_number, created_at, id"
        ),
        {"campaign_id": campaign_id},
    )
    rows = ordered_turns(
        tuple(LegacyTurn.model_validate(dict(row), strict=True) for row in result.mappings())
    )
    if any(row.turn_number > campaign["turn_number"] for row in rows):
        raise ValueError(
            "Legacy history contains a stored future beyond the selected campaign state"
        )
    operations_available = "turn_operations" in tables
    if operations_available:
        raise RuntimeError(
            "Operation-aware campaign capture is unsupported by this offline command"
        )
    turns = tuple(
        BatchTurnSource(
            reference=f"t{index}",
            turn_id=row.id,
            player_action=row.player_action,
            narration=row.narration,
            operations=None,
        )
        for index, row in enumerate(rows, 1)
    )
    return CapturedMemorySource(
        campaign_id=campaign_id, language=campaign["language"], turns=turns
    )


async def capture_readonly(campaign_id: UUID) -> CapturedMemorySource:
    engine = create_async_engine(settings.database_url, isolation_level="REPEATABLE READ")
    try:
        async with engine.connect() as connection, connection.begin():
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            async with AsyncSession(bind=connection) as session:
                return await capture_campaign(session, campaign_id)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture legacy turns for offline memory evaluation"
    )
    parser.add_argument("--campaign", required=True, type=UUID)
    parser.add_argument("--out", required=True, type=Path, help="new output directory")
    parser.add_argument("--batch-size", required=True, type=int)
    args = parser.parse_args()
    source = asyncio.run(capture_readonly(args.campaign))
    batches, tail = partition_capture(source, args.batch_size)
    args.out.mkdir(parents=True, exist_ok=False)
    payloads = {
        "source.json": json.dumps(
            {"source": source.model_dump(mode="json"), "sha256": source.source_hash()},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ),
        "batches.json": json.dumps(
            [batch.model_dump(mode="json") for batch in batches],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ),
        "tail.json": json.dumps(
            [turn.model_dump(mode="json") for turn in tail],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ),
    }
    for filename, content in payloads.items():
        with (args.out / filename).open("x", encoding="utf-8") as output_file:
            output_file.write(content + "\n")
    print(json.dumps({"campaign_id": str(source.campaign_id), "turns": len(source.turns)}))


if __name__ == "__main__":
    main()
