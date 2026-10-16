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
    ("system_node", "cached"),
    [
        ("matching", False),
        ("missing", False),
        ("missing", True),
        ("mismatched", False),
        ("mismatched", True),
    ],
)
def test_node_provisioning(tmp_path: Path, system_node: str, cached: bool) -> None:
    node = shutil.which("node")
    assert node is not None
    original = Path(node).resolve()
    version = subprocess.check_output([node, "--version"], text=True).strip()
    assert version == f"v{VERSION}", "Run these tests with the pinned Node version."

    app = tmp_path / "app with spaces"
    (app / "frontend").mkdir(parents=True)
    (app / "frontend/.node-version").write_text(VERSION + "\n")
    install_root = tmp_path / "install with spaces"
    tools = tmp_path / "tools"
    tools.mkdir()
    if WINDOWS:
        portable = install_root / "node" / f"node-v{VERSION}-win-x64" / "node.exe"
    else:
        os_name = "darwin" if platform.system() == "Darwin" else "linux"
        arch = "arm64" if platform.machine() == "arm64" else "x64"
        portable = install_root / "node" / f"node-v{VERSION}-{os_name}-{arch}" / "bin/node"
        for name in ("uname", "mkdir", "curl", "tar", "rm", "xz", "gzip"):
            executable = shutil.which(name)
            if executable:
                (tools / name).symlink_to(executable)
    if cached:
        portable.parent.mkdir(parents=True)
        shutil.copy2(original, portable)

    env = os.environ.copy()
    env.update(APP_DIR=str(app), INSTALL_ROOT=str(install_root), PATH=str(tools))
    if system_node == "matching":
        env["PATH"] = os.pathsep.join([str(original.parent), str(tools)])
    elif system_node == "mismatched":
        fake = tools / ("node.cmd" if WINDOWS else "node")
        fake.write_text("@echo off\necho v20.18.1\n" if WINDOWS else "#!/bin/sh\necho v20.18.1\n")
        fake.chmod(0o755)

    if WINDOWS:
        shell = shutil.which("pwsh")
        assert shell is not None
        env["SAGA_TEST_SCRIPT"] = str(ROOT / "install/windows/ensure_node.ps1")
        command = [
            shell,
            "-NoProfile",
            "-Command",
            "$ErrorActionPreference = 'Stop'; "
            ". $env:SAGA_TEST_SCRIPT -AppDir $env:APP_DIR -InstallRoot $env:INSTALL_ROOT; "
            "(Get-Command node).Source; node --version",
        ]
    else:
        shell = shutil.which("bash")
        assert shell is not None
        env["SAGA_TEST_SCRIPT"] = str(ROOT / "install/linux-macos/ensure_node.sh")
        command = [
            shell,
            "-c",
            'set -euo pipefail; source "$SAGA_TEST_SCRIPT"; command -v node; node --version',
        ]

    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    selected, selected_version = result.stdout.strip().splitlines()[-2:]
    expected = original if system_node == "matching" else portable
    assert Path(selected).resolve() == expected.resolve()
    assert selected_version == f"v{VERSION}"
    assert portable.exists() is (system_node != "matching")
    if system_node == "mismatched":
        assert "v20.18.1" in fake.read_text()


@pytest.mark.skipif(
    WINDOWS, reason="Windows bootstrap already delegates to the selected checkout."
)
def test_bootstrap_runs_selected_release_installer(tmp_path: Path) -> None:
    app = tmp_path / "app"
    (app / ".git").mkdir(parents=True)
    (app / "backend").mkdir()
    scripts = app / "install/linux-macos"
    scripts.mkdir(parents=True)
    (scripts / "install_saga.sh").write_text('echo "Selected release installer"\n')
    tools = tmp_path / "tools"
    tools.mkdir()
    git = tools / "git"
    git.write_text("#!/bin/sh\nexit 0\n")
    git.chmod(0o755)
    env = os.environ.copy()
    env.update(
        SAGA_FROM_LOCAL="0",
        SAGA_INSTALL_ROOT=str(tmp_path),
        PATH=os.pathsep.join([str(tools), env["PATH"]]),
    )
    result = subprocess.run(
        ["bash", str(ROOT / "install/linux-macos/install_saga.sh")],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().splitlines()[-1] == "Selected release installer"
