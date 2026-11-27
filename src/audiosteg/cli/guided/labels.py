"""How algorithms are named in the menus of the guided mode."""

from questionary import Choice

from audiosteg.algorithms.registry import ALGORITHMS
from audiosteg.core import crypto
from audiosteg.core.signal_algorithm import SignalAlgorithm, has_numpy
from audiosteg.errors import MissingLibraryError

NEEDS_CRYPTO = "Needs [crypto]. "
NEEDS_NUMPY = "Needs NumPy. "


def can_encrypt() -> bool:
    """Say whether this system can encrypt."""
    try:
        crypto.check_available()
    except MissingLibraryError:
        return False
    return True


def missing_library(key: str, encrypts: bool) -> str:
    """Say which library an algorithm needs if it is missing here, or return nothing."""
    algorithm = ALGORITHMS[key]
    if encrypts and algorithm.keyed and not can_encrypt():
        return NEEDS_CRYPTO
    if isinstance(algorithm, SignalAlgorithm) and not has_numpy():
        return NEEDS_NUMPY
    return ""


def algorithm_label(key: str) -> str:
    """Return the key and the name of an algorithm."""
    return f"{key}: {ALGORITHMS[key].name}"


def algorithm_hint(key: str, encrypts: bool = True) -> str:
    """Return the explanation of an algorithm, after the library it needs if that is missing."""
    return f"{missing_library(key, encrypts)}{ALGORITHMS[key].explanation}"


def algorithm_choice(key: str) -> Choice:
    """Return a menu choice for an algorithm, with its hint shown while it is highlighted."""
    return Choice(algorithm_label(key), value=key, description=algorithm_hint(key))


def explain_choice(key: str) -> Choice:
    """Return the same for a menu that never encrypts."""
    return Choice(algorithm_label(key), value=key, description=algorithm_hint(key, encrypts=False))
