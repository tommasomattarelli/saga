import pytest
from sqlalchemy.engine import Row
from sqlalchemy.exc import IntegrityError

from tests.integration.migrations.migration_db import DisposableDatabase
from tests.integration.migrations.test_migration_chain import _insert_campaign, _insert_user

USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CAMPAIGN_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
TURN_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
RUNNING_REQUEST_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
COMMITTED_REQUEST_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
INTERRUPTED_REQUEST_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"
TOKEN_ID = "11111111-1111-1111-1111-111111111111"

_REQUEST_COLUMNS = (
    "request_id, campaign_id, payload_hash, starting_head_turn_id, context_epoch, state, "
    "execution_token, execution_expires_at, claimed_turn_number, result_turn_id, error"
)


async def _request_rows(database: DisposableDatabase) -> list[Row[tuple[object, ...]]]:
    return await database.fetch_all(
        f"SELECT {_REQUEST_COLUMNS} FROM turn_requests ORDER BY request_id"
    )


async def test_014_adds_response_payload_and_downgrades_without_changing_requests() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade("013_turn_operations")
        await _insert_user(database, USER_ID)
        await _insert_campaign(
            database,
            campaign_id=CAMPAIGN_ID,
            user_id=USER_ID,
            world_slug="legacy-world",
            difficulty="MEDIUM",
        )
        await database.execute(
            "INSERT INTO turns (id, campaign_id, turn_number, player_action, narration, "
            "model_used, importance_score, summarization_failed) "
            "VALUES (:id, :campaign, 1, 'Look around.', 'The room is quiet.', 'test-model', 5, false)",
            {"id": TURN_ID, "campaign": CAMPAIGN_ID},
        )
        for request_id, state, token, result_turn_id, turn_number in (
            (RUNNING_REQUEST_ID, "running", TOKEN_ID, None, 1),
            (COMMITTED_REQUEST_ID, "committed", None, TURN_ID, 1),
            (INTERRUPTED_REQUEST_ID, "interrupted", None, None, 2),
        ):
            await database.execute(
                "INSERT INTO turn_requests (request_id, campaign_id, payload_hash, "
                "context_epoch, state, execution_token, execution_expires_at, "
                "claimed_turn_number, result_turn_id) VALUES (:request_id, :campaign, "
                ":payload_hash, 0, :state, :token, "
                "CASE WHEN CAST(:state AS varchar) = 'running' "
                "THEN now() + interval '2 minutes' END, "
                ":turn_number, :result_turn_id)",
                {
                    "request_id": request_id,
                    "campaign": CAMPAIGN_ID,
                    "payload_hash": "a" * 64,
                    "state": state,
                    "token": token,
                    "turn_number": turn_number,
                    "result_turn_id": result_turn_id,
                },
            )
        original_rows = await _request_rows(database)

        await database.upgrade("014_turn_request_responses")

        assert await database.version() == "014_turn_request_responses"
        assert await database.fetch_one(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='turn_requests' "
            "AND column_name='response_payload'"
        ) == ("jsonb", "YES")
        constraint = await database.fetch_one(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid='turn_requests'::regclass "
            "AND conname='ck_turn_requests_response_state'"
        )
        assert constraint is not None
        assert "response_payload" in constraint[0]
        assert await _request_rows(database) == original_rows
        assert await database.fetch_all(
            "SELECT response_payload FROM turn_requests ORDER BY request_id"
        ) == [(None,), (None,), (None,)]

        with pytest.raises(IntegrityError):
            await database.execute(
                "UPDATE turn_requests SET response_payload='{}'::jsonb "
                "WHERE request_id=:request_id",
                {"request_id": RUNNING_REQUEST_ID},
            )
        with pytest.raises(IntegrityError):
            await database.execute(
                "UPDATE turn_requests SET response_payload='[]'::jsonb "
                "WHERE request_id=:request_id",
                {"request_id": COMMITTED_REQUEST_ID},
            )
        await database.execute(
            """UPDATE turn_requests SET response_payload=jsonb_build_object('turn_number', 1)
            WHERE request_id=:request_id""",
            {"request_id": COMMITTED_REQUEST_ID},
        )

        await database.downgrade("013_turn_operations")

        assert await database.version() == "013_turn_operations"
        assert await database.fetch_one("SELECT to_regclass('public.turn_requests')") == (
            "turn_requests",
        )
        assert (
            await database.fetch_all(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='turn_requests' "
                "AND column_name='response_payload'"
            )
            == []
        )
        assert await _request_rows(database) == original_rows
