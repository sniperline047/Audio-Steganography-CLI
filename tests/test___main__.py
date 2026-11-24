"""Tests for audiosteg/__main__.py."""

import subprocess
import sys
from pathlib import Path

PROGRAM = [sys.executable, "-m", "audiosteg"]


def test_the_exit_code_is_passed_on(tmp_path: Path) -> None:
    failed = subprocess.run(PROGRAM, input=b"2\n1\n", capture_output=True, cwd=tmp_path, timeout=60)
    assert failed.returncode == 1
    assert b"Error: The input ended" in failed.stderr
    finished = subprocess.run(PROGRAM, input=b"4\n", capture_output=True, cwd=tmp_path, timeout=60)
    assert (finished.returncode, finished.stderr) == (0, b"")


def test_importing_the_module_does_not_start_the_program() -> None:
    command = [sys.executable, "-c", "import audiosteg.__main__"]
    imported = subprocess.run(command, input=b"9\n", capture_output=True, timeout=60)
    assert (imported.returncode, imported.stdout) == (0, b"")
