import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = platform.system() == "Windows"
VERSION = (ROOT / "frontend/.node-version").read_text().strip()


@pytest.mark.parametrize(
    ("system_node", "exit_code"),
    [("matching", 0), ("missing", 0), ("mismatched", 0), ("mismatched", 7)],
)
@pytest.mark.parametrize(
    "shell_name",
    [
        "bash",
        pytest.param("powershell", marks=pytest.mark.skipif(not WINDOWS, reason="Windows only")),
    ],
)
def test_development_node_selection(
    tmp_path: Path, system_node: str, exit_code: int, shell_name: str
) -> None:
    node = shutil.which("node")
    assert node is not None
    original = Path(node).resolve()
    version = subprocess.check_output([node, "--version"], text=True).strip()
    assert version == f"v{VERSION}", "Run these tests with the pinned Node version."

    app = tmp_path / "app with spaces"
    (app / "frontend").mkdir(parents=True)
    (app / "frontend/.node-version").write_text(VERSION + "\n")
    for relative in [
        "scripts/with_node.sh",
        "scripts/with_node.ps1",
        "install/linux-macos/ensure_node.sh",
        "install/windows/ensure_node.ps1",
    ]:
        source = ROOT / relative
        assert source.is_file(), f"Missing development launcher: {relative}"
        destination = app / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    install_root = tmp_path / "runtime with spaces"
    if WINDOWS:
        portable = install_root / "node" / f"node-v{VERSION}-win-x64" / "node.exe"
    else:
        os_name = "darwin" if platform.system() == "Darwin" else "linux"
        arch = "arm64" if platform.machine() in ("arm64", "aarch64") else "x64"
        portable = install_root / "node" / f"node-v{VERSION}-{os_name}-{arch}" / "bin/node"
    portable.parent.mkdir(parents=True)
    shutil.copy2(original, portable)

    tools = tmp_path / "tools"
    tools.mkdir()
    if WINDOWS:
        path = os.pathsep.join([str(tools), os.environ["SYSTEMROOT"] + r"\System32"])
    else:
        for name in ("dirname", "uname"):
            executable = shutil.which(name)
            assert executable is not None
            (tools / name).symlink_to(executable)
        path = str(tools)
    if system_node == "matching":
        path = os.pathsep.join([str(original.parent), path])
    elif system_node == "mismatched":
        fake = tools / ("node.cmd" if WINDOWS else "node")
        fake.write_text("@echo off\necho v26.8.1\n" if WINDOWS else "#!/bin/sh\necho v26.8.1\n")
        fake.chmod(0o755)

    env = os.environ.copy()
    env.update(PATH=path, SAGA_INSTALL_ROOT=str(install_root))
    if shell_name == "powershell":
        shell = shutil.which("powershell")
        assert shell is not None
        command = [
            shell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(app / "scripts/with_node.ps1"),
        ]
    else:
        shell = shutil.which("bash")
        assert shell is not None
        if WINDOWS:
            git = shutil.which("git")
            assert git is not None
            directories = [Path(git).parent, Path(git).parent.parent / "usr/bin"]
            bash_dir = next(
                directory for directory in directories if (directory / "uname.exe").is_file()
            )
            shell = str(bash_dir / "bash.exe")
            powershell = shutil.which("powershell")
            assert powershell is not None
            env["PATH"] = os.pathsep.join([path, str(bash_dir), str(Path(powershell).parent)])
        command = [shell, (app / "scripts/with_node.sh").as_posix()]

    caller = tmp_path / "caller with spaces"
    caller.mkdir()
    arguments = ["value with spaces", "--sample=one", "-Command", "-ErrorAction"]
    # Spaces keep this argument quoted when Windows joins the command line;
    # an unquoted brace group would be expanded by the MSYS shell.
    script = (
        "console.log(JSON.stringify({ version: process.version,"
        " cwd: process.cwd(),"
        " args: process.argv.slice(1) }));"
        f" process.exit({exit_code})"
    )
    result = subprocess.run(
        [*command, "node", "-e", script, *arguments],
        cwd=caller,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == exit_code, result.stdout + result.stderr
    data = json.loads(result.stdout.strip())
    assert data == {"version": f"v{VERSION}", "cwd": str(caller), "args": arguments}
    if system_node == "mismatched":
        assert "v26.8.1" in fake.read_text()


def test_frontend_hooks_use_the_development_launcher() -> None:
    entries = [
        line.strip()
        for line in (ROOT / ".pre-commit-config.yaml").read_text().splitlines()
        if "entry:" in line and "cd frontend" in line
    ]
    assert len(entries) == 4
    assert all("bash ../scripts/with_node.sh " in entry for entry in entries)
