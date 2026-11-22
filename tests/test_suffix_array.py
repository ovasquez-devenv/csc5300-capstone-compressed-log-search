"""Suffix array construction and binary-search locate."""

import random

import numpy as np
import pytest

from logsieve.suffix_array import (
    build_suffix_array,
    naive_suffix_array,
    suffix_array_search,
)


def test_empty_text():
    sa = build_suffix_array(b"")
    assert sa.tolist() == []


def test_single_character():
    assert build_suffix_array(b"a").tolist() == [0]


def test_matches_naive_on_small_strings():
    rng = random.Random(5300)
    samples = [b"banana\x00", b"aaaa", b"abc", b"\x00", b"mississippi\x00"]
    for _ in range(15):
        n = rng.randint(1, 40)
        samples.append(bytes(rng.randrange(1, 6) for _ in range(n)) + b"\x00")
    for text in samples:
        got = build_suffix_array(text).tolist()
        assert got == naive_suffix_array(text)


def test_is_sorted_permutation_on_longer_random_text():
    rng = random.Random(7)
    text = bytes(rng.randrange(0, 8) for _ in range(400)) + b"\x00"
    sa = build_suffix_array(text)
    assert sorted(sa.tolist()) == list(range(len(text)))
    for i in range(len(text) - 1):
        assert text[int(sa[i]) :] <= text[int(sa[i + 1]) :]


def test_binary_search_matches_naive_scan():
    from logsieve.baselines import naive_search

    text = b"banana\x00"
    sa = build_suffix_array(text)
    for pattern in (b"", b"a", b"na", b"ana", b"banana", b"x", b"bananaz", b"\x00"):
        assert suffix_array_search(text, sa, pattern) == naive_search(text, pattern)


def test_binary_search_overlapping_and_edges():
    from logsieve.baselines import naive_search

    text = b"aaaa\x00"
    sa = build_suffix_array(text)
    assert suffix_array_search(text, sa, b"aa") == naive_search(text, b"aa")
    assert suffix_array_search(text, sa, b"aaaa") == [0]
    text = b"xyzxyz\x00"
    sa = build_suffix_array(text)
    assert suffix_array_search(text, sa, b"xyz") == [0, 3]
    assert suffix_array_search(text, sa, b"z") == [2, 5]


def test_rejects_non_bytes():
    with pytest.raises(TypeError):
        build_suffix_array("abc")  # type: ignore[arg-type]


def test_suffix_array_dtype():
    sa = build_suffix_array(b"abc\x00")
    assert sa.dtype == np.int32
