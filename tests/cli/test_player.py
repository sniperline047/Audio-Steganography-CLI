"""Tests for audiosteg/cli/player.py. No test plays sound."""

import subprocess
import sys
from typing import Any

import pytest


@pytest.mark.parametrize("player", ["/usr/bin/afplay", "/usr/bin/aplay", "paplay", "ffplay.exe"])
def test_no_test_can_start_a_real_player(run_process: Any, player: str) -> None:
    with pytest.raises(AssertionError, match="tried to play sound"):
        subprocess.Popen([player, "no such file.wav"])
    code = f"import subprocess; subprocess.Popen([{player!r}, 'no such file.wav'])"
    with pytest.raises(AssertionError, match="Traceback"):
        run_process(command=[sys.executable, "-c", code])


@pytest.mark.skipif(sys.platform != "win32", reason="only Windows can play sound itself")
def test_no_test_can_play_sound_with_windows() -> None:
    import winsound

    with pytest.raises(AssertionError, match="tried to play sound"):
        winsound.PlaySound(None, 0)
