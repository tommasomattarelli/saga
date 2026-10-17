import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = sys.platform == "win32"


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (None, ["up", "backend", "frontend", "down"]),
        ("up", ["up", "down"]),
        ("backend", ["up", "backend", "down"]),
        ("frontend", ["up", "backend", "frontend", "down"]),
        ("down", ["up", "backend", "frontend", "down"]),
    ],
)
def test_full_suite_lifecycle(tmp_path: Path, failure: str | None, expected: list[str]) -> None:
    make = shutil.which("make")
    assert make is not None
    recorder = tmp_path / "record.py"
    recorder.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "with Path('events.txt').open('a', encoding='utf-8') as events:\n"
        "    events.write(sys.argv[1] + '\\n')\n"
        "sys.exit(int(sys.argv[2]))\n"
    )
    python = f'{"& " if WINDOWS else ""}"{sys.executable}" record.py'

    def command(stage: str) -> str:
        return f"{python} {stage} {9 if stage == failure else 0}"

    makefile = (ROOT / "Makefile").as_posix().replace(" ", r"\ ")
    (tmp_path / "Makefile").write_text(
        f"include {makefile}\n"
        f"RUN_FULL_SUITE := {command('backend')}\n"
        f"test-infra-up:\n\t@{command('up')}\n"
        f"test-infra-down:\n\t@{command('down')}\n"
        f"test-frontend:\n\t@{command('frontend')}\n"
    )
    env = os.environ.copy()
    env["MAKE"] = make
    result = subprocess.run(
        [make, "test-all"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert (tmp_path / "events.txt").read_text(encoding="utf-8").splitlines() == expected
    assert (result.returncode == 0) is (failure is None), result.stdout + result.stderr


def test_test_database_mount_uses_shared_selinux_label() -> None:
    mounts = [
        line.strip()
        for line in (ROOT / "docker-compose.test.yml").read_text().splitlines()
        if "./init.sql:" in line
    ]
    assert mounts == ["- ./init.sql:/docker-entrypoint-initdb.d/init.sql:z"]
