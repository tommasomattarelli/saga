import os
from unittest.mock import patch

from eval.memory.run_lock import evidence_run_lock


def test_run_lock_closes_its_descriptor_exactly_once(tmp_path) -> None:
    with patch("eval.memory.run_lock.os.close", wraps=os.close) as close:
        with evidence_run_lock(tmp_path):
            assert (tmp_path / ".run.lock").exists()
        assert close.call_count == 1
    assert not (tmp_path / ".run.lock").exists()
