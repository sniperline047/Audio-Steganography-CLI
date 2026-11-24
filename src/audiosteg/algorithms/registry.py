"""The list of available algorithms."""

from audiosteg.algorithms.basic_lsb import BASIC_LSB
from audiosteg.algorithms.enhanced_lsb import ENHANCED_LSB
from audiosteg.algorithms.enhanced_lsb_flip import ENHANCED_LSB_FLIP
from audiosteg.core.algorithm import Algorithm

ALGORITHMS: dict[int, Algorithm] = {
    1: BASIC_LSB,
    2: ENHANCED_LSB_FLIP,
    3: ENHANCED_LSB,
}
