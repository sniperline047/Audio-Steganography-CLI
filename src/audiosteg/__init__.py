"""Hide text messages in WAV files and read them back."""

from audiosteg.algorithms.detection import decode
from audiosteg.core.algorithm import Algorithm
from audiosteg.core.stego_file import encode
from audiosteg.errors import (
    CapacityError,
    DamagedMessageError,
    InvalidMessageError,
    MissingLibraryError,
    NoMessageError,
    NotEncryptedError,
    PassphraseRequiredError,
    StegoError,
    UnsafeOutputError,
    UnsuitableAudioError,
    UnsupportedAlgorithmError,
    UnsupportedFormatError,
    WrongPassphraseError,
)

__all__ = [
    "Algorithm",
    "CapacityError",
    "DamagedMessageError",
    "InvalidMessageError",
    "MissingLibraryError",
    "NoMessageError",
    "NotEncryptedError",
    "PassphraseRequiredError",
    "StegoError",
    "UnsafeOutputError",
    "UnsuitableAudioError",
    "UnsupportedAlgorithmError",
    "UnsupportedFormatError",
    "WrongPassphraseError",
    "decode",
    "encode",
]
