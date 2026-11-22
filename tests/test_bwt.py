"""BWT construction and inverse."""

import random

from logsieve.bwt import burrows_wheeler, c_table, inverse_bwt
from logsieve.suffix_array import build_suffix_array


def test_banana_bwt():
    text = b"banana\x00"
    sa = build_suffix_array(text)
    assert sa.tolist() == [6, 5, 3, 1, 0, 4, 2]
    assert burrows_wheeler(text, sa) == b"annb\x00aa"


def test_round_trip_fixed_strings():
    for text in (b"\x00", b"a\x00", b"banana\x00", b"aaaa\x00", b"mississippi\x00"):
        assert inverse_bwt(burrows_wheeler(text)) == text


def test_round_trip_random():
    rng = random.Random(5300)
    for n in (1, 2, 5, 30, 200):
        body = bytes(rng.randrange(1, 12) for _ in range(n))
        text = body + b"\x00"
        assert inverse_bwt(burrows_wheeler(text)) == text


def test_c_table_counts_smaller_symbols():
    table = c_table(b"annb\x00aa")
    # symbols: 0x00 once, a three times, b once, n twice
    assert table[0] == 0
    assert table[ord("a")] == 1
    assert table[ord("b")] == 4
    assert table[ord("n")] == 5
    assert table[ord("n") + 1] == 7


def test_inverse_requires_one_sentinel():
    import pytest

    with pytest.raises(ValueError):
        inverse_bwt(b"abc")
    with pytest.raises(ValueError):
        inverse_bwt(b"a\x00b\x00")


def test_bwt_builds_its_own_suffix_array():
    text = b"hello\x00"
    assert burrows_wheeler(text) == burrows_wheeler(text, build_suffix_array(text))
