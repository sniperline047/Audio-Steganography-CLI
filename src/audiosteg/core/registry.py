"""Default paths and the list of available algorithms."""

from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

from algorithms import (
    basic_lsb_steganography,
    enhanced_lsb_steganography_no_flip,
    enhanced_lsb_steganography_with_flip,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STANDARD_INPUT_FILE_PATH = str(PROJECT_ROOT / "input" / "original_sample.wav")
OUTPUT_BASIC_LSB = str(PROJECT_ROOT / "output" / "basic_lsb_encoded.wav")
OUTPUT_ENHANCED_LSB_FLIP = str(PROJECT_ROOT / "output" / "enhanced_lsb_encoded_flip.wav")
OUTPUT_ENHANCED_LSB_NO_FLIP = str(PROJECT_ROOT / "output" / "enhanced_lsb_encoded_no_flip.wav")


class Algorithm(TypedDict):
    """One entry in the algorithm menu."""

    name: str
    encode: Callable[[str, str, str, bool], None]
    decode: Callable[[str], str]
    output_file: str


ALGORITHMS: dict[int, Algorithm] = {
    1: {
        "name": "Basic LSB Steganography",
        "encode": basic_lsb_steganography.encode,
        "decode": basic_lsb_steganography.decode,
        "output_file": OUTPUT_BASIC_LSB,
    },
    2: {
        "name": "Enhanced LSB Steganography with Bit Flipping",
        "encode": enhanced_lsb_steganography_with_flip.encode,
        "decode": enhanced_lsb_steganography_with_flip.decode,
        "output_file": OUTPUT_ENHANCED_LSB_FLIP,
    },
    3: {
        "name": "Enhanced LSB Steganography without Bit Flipping",
        "encode": enhanced_lsb_steganography_no_flip.encode,
        "decode": enhanced_lsb_steganography_no_flip.decode,
        "output_file": OUTPUT_ENHANCED_LSB_NO_FLIP,
    },
}
