"""Plain integer seeds for reproducible random draws.

A seed is built by writing each integer part with a fixed number of digits and
reading the result as one number, so the parts (12, 2003, 4) give the digits
000012 002003 000004. Callers pass integers such as a station's position in a
sorted roster, a year or a design index; nothing is derived from text.
"""

from __future__ import annotations

from collections.abc import Iterable, Hashable

SEED_MODULUS = 2**32
LONG_SEED_MODULUS = 2**32 - 5  # a prime, so every part of a long seed changes the result
PLAIN_PARTS = 4


def plain_seed(*parts: int, width: int = 6) -> int:
    """Join non-negative integers into one reproducible random seed.

    With up to four parts the digits are read as one number reduced modulo 2**32.
    Longer seeds would lose their leading parts under that reduction, so they use
    the same digits reduced modulo the prime 2**32 - 5 instead.
    """

    seed = 0
    for part in parts:
        value = int(part)
        if value < 0:
            raise ValueError("seed parts must be non-negative integers")
        seed = seed * 10**width + value % 10**width
    return seed % (SEED_MODULUS if len(parts) <= PLAIN_PARTS else LONG_SEED_MODULUS)


def position_index(values: Iterable[Hashable]) -> dict:
    """Map each distinct value to its position in sorted order."""

    return {value: index for index, value in enumerate(sorted(set(values), key=str))}
