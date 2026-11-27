"""Errors that explain why a steganography operation could not finish."""


class StegoError(Exception):
    """Base class for every error this project raises on purpose."""


class CapacityError(StegoError):
    """The message does not fit in the audio file."""


class NoMessageError(StegoError):
    """The audio file does not hold a readable hidden message."""


class UnsupportedFormatError(StegoError):
    """The WAV file or the hidden message has a format that cannot be read."""


class InvalidMessageError(StegoError):
    """The message cannot be stored as UTF-8 text."""


class UnsafeOutputError(StegoError):
    """The output path could damage another file."""


class UnsuitableAudioError(StegoError):
    """The sound cannot carry the message, although it is long enough."""


class UnsupportedAlgorithmError(StegoError):
    """The algorithm cannot hide new messages."""


class DamagedMessageError(StegoError):
    """A hidden message was found, but it was changed or cut off."""


class PassphraseRequiredError(StegoError):
    """The message is encrypted and no passphrase was given."""


class NotEncryptedError(StegoError):
    """A passphrase was given for a message that is not encrypted."""


class WrongPassphraseError(StegoError):
    """The passphrase is wrong, or the encrypted message was changed."""


class MissingLibraryError(StegoError):
    """An optional library is not available, for example because it is not installed."""
