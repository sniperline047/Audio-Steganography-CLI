"""What the commands found or did, without any formatting."""

from dataclasses import dataclass, field

from audiosteg.cli.accuracy import AccuracyResult


@dataclass(frozen=True)
class HideResult:
    """
    A message was hidden.

    :param gain: What every sample was multiplied by: 1, or less if the result would be too loud
    """

    input_file: str
    output_file: str
    algorithm: str
    encrypted: bool
    gain: float = 1.0


@dataclass(frozen=True)
class RevealResult:
    """A message was found."""

    file: str
    algorithm: str
    legacy: bool
    encrypted: bool
    message: str = field(repr=False)


@dataclass(frozen=True)
class VerifyResult:
    """A message was found and compared with the expected one."""

    revealed: RevealResult
    accuracy: AccuracyResult
