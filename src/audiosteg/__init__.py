"""Hide text messages in WAV files and read them back."""

from audiosteg.core.algorithm import Algorithm
from audiosteg.core.stego_file import decode, encode
from audiosteg.errors import (
    CapacityError,
    InvalidMessageError,
    NoMessageError,
    StegoError,
    UnsafeOutputError,
    UnsupportedFormatError,
)

__all__ = [
    "Algorithm",
    "CapacityError",
    "InvalidMessageError",
    "NoMessageError",
    "StegoError",
    "UnsafeOutputError",
    "UnsupportedFormatError",
    "decode",
    "encode",
]
