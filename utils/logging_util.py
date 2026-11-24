"""Logging setup shared by every module."""

import logging


def setup_logger(name: str) -> logging.Logger:
    """
    Set up a logger that only shows warnings and errors.

    Never log secret messages. Log their length at most.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.WARNING)
    if not logger.hasHandlers():
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger
