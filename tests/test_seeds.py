from __future__ import annotations

import pytest

from stream_recoverability.seeds import plain_seed, position_index


def test_short_seed_reads_digits_as_one_number():
    assert plain_seed(12, 2003, 4) == 12002003000004 % 2**32


def test_every_part_of_a_long_seed_matters():
    base = (7, 11, 13, 17, 19, 23, 29)
    seeds = {plain_seed(*base)}
    for index in range(len(base)):
        changed = list(base)
        changed[index] += 1
        seeds.add(plain_seed(*changed))
    assert len(seeds) == len(base) + 1


def test_seed_is_a_valid_numpy_seed_and_rejects_negative_parts():
    assert 0 <= plain_seed(1, 2, 3, 4, 5, 6) < 2**32
    with pytest.raises(ValueError):
        plain_seed(1, -2)


def test_position_index_is_sorted_and_deterministic():
    assert position_index(["b", "a", "b", "c"]) == {"a": 0, "b": 1, "c": 2}
