import json
from unittest.mock import AsyncMock

import dialogue_suite
from dialogue_suite import append_evidence, manifest, read_evidence


def test_manifest_is_repeatable_and_accounts_for_all_model_repetitions():
    first = manifest()
    assert first == manifest()
    assert first["trials"] == 36
    assert first["nominal_requests"] == 66
    assert first["request_ceiling"] == 72
    assert first["pipeline_dm_cap"] == 3


async def test_dry_run_does_not_resolve_profiles_or_contact_catalog(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("No network or database access in dry-run")

    monkeypatch.setattr("socket.socket.connect", forbidden)
    resolve = AsyncMock(side_effect=forbidden)
    catalog = AsyncMock(side_effect=forbidden)
    monkeypatch.setattr(dialogue_suite, "resolve_eval_generation", resolve)
    monkeypatch.setattr(dialogue_suite, "validate_free_models", catalog)
    monkeypatch.setattr("sys.argv", ["dialogue_suite.py", "--dry-run"])
    await dialogue_suite.main()
    assert json.loads(capsys.readouterr().out)["trials"] == 36
    resolve.assert_not_called()
    catalog.assert_not_called()


def test_interrupted_trial_is_distinct_from_a_completed_trial(tmp_path):
    path = tmp_path / "trials.jsonl"
    append_evidence(path, {"event": "started", "key": "one"})
    rows, interrupted = read_evidence(path)
    assert rows == {} and interrupted == {"one"}
    append_evidence(path, {"event": "result", "key": "one", "requests": 2})
    rows, interrupted = read_evidence(path)
    assert rows["one"]["requests"] == 2 and not interrupted


def test_retry_attempt_supersedes_only_when_its_result_lands(tmp_path):
    path = tmp_path / "trials.jsonl"
    append_evidence(path, {"event": "started", "key": "one"})
    append_evidence(path, {"event": "result", "key": "one", "requests": 1, "retryable": True})
    append_evidence(path, {"event": "started", "key": "one"})
    rows, interrupted = read_evidence(path)
    assert rows["one"]["retryable"] and interrupted == {"one"}
    append_evidence(path, {"event": "result", "key": "one", "requests": 1, "retryable": False})
    rows, interrupted = read_evidence(path)
    assert not rows["one"]["retryable"] and not interrupted
