"""Request ledger for live evaluation runs.

Quota is the binding constraint of a live run: an unaccounted call cannot be
resumed and an overshoot cannot be undone. Every attempt is reserved on disk
before the provider call and completed after it, so an interrupted run leaves an
exact checkpoint: what was spent, what finished, what was cut mid-flight.

The ledger counts *requests*, not cases. A failed or retried attempt is still a
request; actor fan-out is visible because each actor call gets its own key.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


class BudgetExhaustedError(RuntimeError):
    """The next call would exceed the configured request budget."""


@dataclass
class Attempt:
    key: str
    scenario: str
    probe: str
    run: int
    status: str = "reserved"  # reserved | ok | error
    failed: list[str] = field(default_factory=list)
    seconds: float = 0.0
    error: str = ""
    at: str = ""


class RequestLedger:
    """Append-only JSONL ledger shared by the DM and actor paths."""

    def __init__(self, path: Path | str, budget: int | None = None) -> None:
        self.path = Path(path)
        self.budget = budget
        self._reserved: list[str] = []
        self._results: dict[str, Attempt] = {}
        if self.path.exists():
            self._replay()

    @property
    def spent(self) -> int:
        return len(self._reserved)

    @property
    def remaining(self) -> int | None:
        if self.budget is None:
            return None
        return max(0, self.budget - self.spent)

    def completed(self, key: str) -> bool:
        return key in self._results

    def results(self) -> list[Attempt]:
        """Completed attempts in the order they were recorded."""
        return list(self._results.values())

    def interrupted(self) -> list[str]:
        """Reserved but never completed — a crash or a killed process."""
        return [key for key in self._reserved if key not in self._results]

    def reserve(self, attempt: Attempt) -> None:
        if self.completed(attempt.key):
            raise ValueError(f"attempt already completed: {attempt.key}")
        if self.budget is not None and self.spent >= self.budget:
            raise BudgetExhaustedError(
                f"budget exhausted: {self.spent}/{self.budget} requests spent"
            )
        self._reserved.append(attempt.key)
        self._write({"event": "reserve", **asdict(attempt)})

    def record(self, attempt: Attempt) -> None:
        attempt.at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._results[attempt.key] = attempt
        self._write({"event": "result", **asdict(attempt)})

    def _replay(self) -> None:
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            key = str(data["key"])
            if data.get("event") == "reserve":
                self._reserved.append(key)
                continue
            self._results[key] = Attempt(
                key=key,
                scenario=str(data.get("scenario", "")),
                probe=str(data.get("probe", "")),
                run=int(data.get("run", 0)),
                status=str(data.get("status", "ok")),
                failed=list(data.get("failed") or []),
                seconds=float(data.get("seconds", 0.0)),
                error=str(data.get("error", "")),
                at=str(data.get("at", "")),
            )

    def _write(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
