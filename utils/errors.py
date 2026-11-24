"""Errors that explain why a steganography operation could not finish."""


class StegoError(Exception):
    """Base class for every error this project raises on purpose."""


class CapacityError(StegoError):
    """The message does not fit in the audio file."""


class NoMessageError(StegoError):
    """The audio file does not hold a readable hidden message."""


class UnsupportedFormatError(StegoError):
    """The input is not an uncompressed PCM WAV file."""


class InvalidMessageError(StegoError):
    """The message cannot be stored as UTF-8 text."""


class UnsafeOutputError(StegoError):
    """The output path could damage another file."""
