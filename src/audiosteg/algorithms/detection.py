"""Find out which algorithm hid a message, and read the message."""

from audiosteg.algorithms.legacy import decode_legacy
from audiosteg.algorithms.lsb_keyed import LSB_KEYED
from audiosteg.algorithms.registry import ALGORITHMS
from audiosteg.core import stego_file
from audiosteg.core.algorithm import Algorithm, LegacyAlgorithm
from audiosteg.core.crypto import passphrase_to_bytes
from audiosteg.core.header import Header
from audiosteg.core.signal_algorithm import SignalAlgorithm, has_numpy
from audiosteg.errors import NoMessageError, NotEncryptedError


def can_detect(algorithm: Algorithm | SignalAlgorithm) -> bool:
    """Say whether messages of an algorithm can be detected here without a passphrase."""
    return algorithm.detectable and (not isinstance(algorithm, SignalAlgorithm) or has_numpy())


def undetectable_here() -> tuple[str, ...]:
    """Return the names of the algorithms whose messages could be detected if NumPy was installed."""
    return tuple(key for key, known in ALGORITHMS.items() if known.detectable and not can_detect(known))


def detect(path: str) -> tuple[Algorithm | SignalAlgorithm, Header] | None:
    """Return the first algorithm that finds a message without a passphrase, with its header, or None."""
    for algorithm in ALGORITHMS.values():
        if not can_detect(algorithm):
            continue
        header = stego_file.read_header(path, algorithm)
        if header is not None:
            return algorithm, header
    return None


def decode(
    path: str,
    algorithm: Algorithm | SignalAlgorithm | LegacyAlgorithm | None = None,
    *,
    passphrase: str | None = None,
) -> str:
    """
    Read a hidden message from a WAV file.

    :param path: Path to the encoded audio file
    :param algorithm: The algorithm that hid the message, or None to detect it. Files made by
        older versions are not detected and need a legacy algorithm.
    :param passphrase: The passphrase of an encrypted message. It is refused if the message
        is not encrypted. If no message is detected, it is also tried on LSB_KEYED.
    :return: The hidden message
    """
    if passphrase is not None:
        passphrase_to_bytes(passphrase)
    if isinstance(algorithm, LegacyAlgorithm):
        if passphrase is not None:
            raise NotEncryptedError("Older versions never encrypted messages. Remove the passphrase.")
        return decode_legacy(path, algorithm)
    if algorithm is None:
        detected = detect(path)
        if detected is None and passphrase is not None:
            return stego_file.decode(path, LSB_KEYED, passphrase=passphrase)
        if detected is None:
            raise NoMessageError("No hidden message was found.")
        algorithm = detected[0]
    return stego_file.decode(path, algorithm, passphrase=passphrase)
