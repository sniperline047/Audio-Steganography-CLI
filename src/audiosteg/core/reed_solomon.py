"""
Correct wrong bytes with a Reed-Solomon code.

The bytes are numbers of the finite field GF(256), where adding is XOR, and every result is a byte again.
Parity bytes are added so that the whole codeword, seen as a polynomial, is 0 at some known points.
Wrong bytes make it differ from 0 there, and these differences tell which bytes are wrong, and by how much.
"""

from collections.abc import Sequence

FIELD_POLYNOMIAL = 0x11D
LONGEST = 255


def make_tables() -> tuple[list[int], list[int]]:
    """Return the powers of 2 in the field, twice in a row, and the exponent of each number from 1 on."""
    powers, exponents = [0] * (2 * LONGEST), [0] * (LONGEST + 1)
    value = 1
    for exponent in range(LONGEST):
        powers[exponent] = powers[exponent + LONGEST] = value
        exponents[value] = exponent
        value <<= 1
        if value > LONGEST:
            value ^= FIELD_POLYNOMIAL
    return powers, exponents


POWERS, EXPONENTS = make_tables()


class TooManyErrorsError(Exception):
    """More bytes are wrong than the parity bytes can correct."""


def multiply(first: int, second: int) -> int:
    """Multiply two numbers of the field."""
    if first == 0 or second == 0:
        return 0
    return POWERS[EXPONENTS[first] + EXPONENTS[second]]


def divide(first: int, second: int) -> int:
    """Divide by a number of the field that is not 0."""
    if first == 0:
        return 0
    return POWERS[EXPONENTS[first] + LONGEST - EXPONENTS[second]]


def evaluate(polynomial: Sequence[int], point: int) -> int:
    """Return the value of a polynomial, highest power first, at a point that is not 0."""
    step = EXPONENTS[point]
    value = 0
    for coefficient in polynomial:
        value = POWERS[EXPONENTS[value] + step] ^ coefficient if value else coefficient
    return value


def multiply_polynomials(first: Sequence[int], second: Sequence[int]) -> list[int]:
    """Multiply two polynomials. The order of their powers must be the same."""
    product = [0] * (len(first) + len(second) - 1)
    for i, left in enumerate(first):
        for j, right in enumerate(second):
            product[i + j] ^= multiply(left, right)
    return product


def generator(parity_size: int) -> list[int]:
    """Return the polynomial that is 0 at the first powers of 2, highest power first."""
    polynomial = [1]
    for exponent in range(parity_size):
        polynomial = multiply_polynomials(polynomial, [1, POWERS[exponent]])
    return polynomial


def make_parity(data: bytes, parity_size: int) -> bytes:
    """
    Return the parity bytes of some data: the remainder after dividing by the generator.

    :param data: The bytes to protect
    :param parity_size: How many parity bytes to make. Half as many wrong bytes can be corrected.
    """
    if len(data) + parity_size > LONGEST:
        raise ValueError(f"A codeword has at most {LONGEST} bytes.")
    divisor = generator(parity_size)[1:]
    remainder = [0] * parity_size
    for byte in data:
        factor = byte ^ remainder[0]
        remainder = [*remainder[1:], 0]
        for index, coefficient in enumerate(divisor):
            remainder[index] ^= multiply(factor, coefficient)
    return bytes(remainder)


def find_syndromes(codeword: Sequence[int], parity_size: int) -> list[int]:
    """Return the values at the known points. Without errors, all of them are 0."""
    return [evaluate(codeword, POWERS[exponent]) for exponent in range(parity_size)]


def find_locator(syndromes: Sequence[int]) -> list[int]:
    """
    Return the polynomial, lowest power first, that is 0 where the errors are (Berlekamp-Massey).

    It is the shortest rule that predicts every syndrome from the ones before.
    """
    locator, previous = [1], [1]
    errors, shift, last_difference = 0, 1, 1
    for number, syndrome in enumerate(syndromes):
        difference = syndrome
        for index in range(1, min(errors, len(locator) - 1) + 1):
            difference ^= multiply(locator[index], syndromes[number - index])
        if difference == 0:
            shift += 1
            continue
        factor = divide(difference, last_difference)
        correction = [0] * shift + [multiply(factor, value) for value in previous]
        size = max(len(locator), len(correction))
        longer = [*locator, *[0] * (size - len(locator))]
        for index, value in enumerate(correction):
            longer[index] ^= value
        if 2 * errors <= number:
            previous, last_difference = locator, difference
            errors, shift = number + 1 - errors, 1
        else:
            shift += 1
        locator = longer
    return locator[: errors + 1]


def find_positions(locator: Sequence[int], length: int) -> list[int]:
    """Return the exponents of the wrong bytes, counted from the end of the codeword."""
    highest_first = locator[::-1]
    return [
        position
        for position in range(length)
        if evaluate(highest_first, POWERS[(LONGEST - position) % LONGEST]) == 0
    ]


def find_error(syndromes: Sequence[int], locator: Sequence[int], position: int) -> int:
    """Return by how much the byte at a position is wrong (Forney's formula)."""
    inverse = POWERS[(LONGEST - position) % LONGEST]
    evaluator = multiply_polynomials(syndromes, locator)[: len(syndromes)]
    derivative = [value if index % 2 else 0 for index, value in enumerate(locator)][1:]
    slope = evaluate(derivative[::-1], inverse)
    return multiply(POWERS[position], divide(evaluate(evaluator[::-1], inverse), slope))


def correct(codeword: bytes, parity_size: int) -> tuple[bytes, int]:
    """
    Correct a codeword. More errors than half of the parity bytes are almost always noticed, but not always.

    :param codeword: The data and its parity bytes
    :param parity_size: How many of the last bytes are parity bytes
    :return: The data, and how many bytes of the codeword were wrong
    """
    syndromes = find_syndromes(codeword, parity_size)
    if not any(syndromes):
        return codeword[: len(codeword) - parity_size], 0
    locator = find_locator(syndromes)
    errors = len(locator) - 1
    if errors > parity_size // 2:
        raise TooManyErrorsError
    positions = find_positions(locator, len(codeword))
    if len(positions) != errors:
        raise TooManyErrorsError
    corrected = bytearray(codeword)
    for position in positions:
        corrected[-1 - position] ^= find_error(syndromes, locator, position)
    return bytes(corrected[: len(corrected) - parity_size]), errors
