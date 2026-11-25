"""How algorithms are named in the menus of the guided mode."""

from audiosteg.algorithms.registry import ALGORITHMS
from audiosteg.core import crypto
from audiosteg.errors import MissingLibraryError

NOT_AVAILABLE = " (needs encryption, which is not available here)"


def can_encrypt() -> bool:
    """Say whether this system can encrypt."""
    try:
        crypto.check_available()
    except MissingLibraryError:
        return False
    return True


def algorithm_label(key: str) -> str:
    """Return the name and the explanation of an algorithm, and whether it cannot be used here."""
    algorithm = ALGORITHMS[key]
    missing = NOT_AVAILABLE if algorithm.keyed and not can_encrypt() else ""
    return f"{key}{missing}: {algorithm.explanation}"
