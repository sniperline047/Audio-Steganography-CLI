"""How algorithms are named in the menus of the guided mode."""

from questionary import Choice

from audiosteg.algorithms.registry import ALGORITHMS
from audiosteg.core import crypto
from audiosteg.core.signal_algorithm import SignalAlgorithm, has_numpy
from audiosteg.errors import MissingLibraryError

NOT_AVAILABLE = " (cannot encrypt here)"
NO_NUMPY = " (needs NumPy)"


def can_encrypt() -> bool:
    """Say whether this system can encrypt."""
    try:
        crypto.check_available()
    except MissingLibraryError:
        return False
    return True


def no_numpy(key: str) -> str:
    """Say that an algorithm needs NumPy if it does and NumPy is missing."""
    return NO_NUMPY if isinstance(ALGORITHMS[key], SignalAlgorithm) and not has_numpy() else ""


def algorithm_label(key: str) -> str:
    """Return the key and the name of an algorithm, and whether it cannot be used here."""
    algorithm = ALGORITHMS[key]
    missing = NOT_AVAILABLE if algorithm.keyed and not can_encrypt() else no_numpy(key)
    return f"{key}{missing}: {algorithm.name}"


def explain_label(key: str) -> str:
    """Return the same for a menu that never encrypts."""
    return f"{key}{no_numpy(key)}: {ALGORITHMS[key].name}"


def algorithm_choice(key: str) -> Choice:
    """Return a menu choice for an algorithm, with its explanation shown while it is highlighted."""
    return Choice(algorithm_label(key), value=key, description=ALGORITHMS[key].explanation)


def explain_choice(key: str) -> Choice:
    """Return the same for a menu that never encrypts."""
    return Choice(explain_label(key), value=key, description=ALGORITHMS[key].explanation)
