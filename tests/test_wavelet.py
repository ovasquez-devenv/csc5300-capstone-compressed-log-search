"""Wavelet tree rank, access, and the bit vector under it."""

import random

import pytest

from logsieve.wavelet import RankBitVector, WaveletTree
import numpy as np


def test_rank_and_access_on_a_short_vector():
    bits = np.array([1, 0, 1, 1, 0, 0, 1], dtype=np.uint8)
    vector = RankBitVector(bits)
    assert [vector.access(i) for i in range(7)] == [1, 0, 1, 1, 0, 0, 1]
    assert [vector.rank1(i) for i in range(8)] == [0, 1, 1, 2, 3, 3, 3, 4]
    assert vector.rank0(4) == 1
    assert vector.select1(1) == 0
    assert vector.select1(2) == 2
    assert vector.select1(4) == 6
    with pytest.raises(ValueError):
        vector.select1(5)


def test_rank_across_block_boundaries():
    rng = random.Random(5300)
    bits = np.array([rng.randrange(2) for _ in range(2000)], dtype=np.uint8)
    vector = RankBitVector(bits)
    running = 0
    for i, bit in enumerate(bits.tolist()):
        assert vector.rank1(i) == running
        assert vector.access(i) == bit
        running += bit
    assert vector.rank1(len(bits)) == running
    ones = [i for i, bit in enumerate(bits.tolist()) if bit]
    for k, pos in enumerate(ones, start=1):
        assert vector.select1(k) == pos


def test_wavelet_rank_and_access_match_the_string():
    rng = random.Random(11)
    data = bytes(rng.randrange(0, 20) for _ in range(500))
    tree = WaveletTree(data)
    for i, symbol in enumerate(data):
        assert tree.access(i) == symbol
    for symbol in range(20):
        running = 0
        for i, current in enumerate(data):
            assert tree.rank(symbol, i) == running
            if current == symbol:
                running += 1
        assert tree.rank(symbol, len(data)) == running
    assert tree.rank(255, len(data)) == 0


def test_wavelet_single_symbol_and_empty():
    tree = WaveletTree(b"zzzz")
    assert tree.access(2) == ord("z")
    assert tree.rank(ord("z"), 4) == 4
    assert tree.rank(ord("a"), 4) == 0
    empty = WaveletTree(b"")
    assert empty.rank(ord("a"), 0) == 0
    with pytest.raises(IndexError):
        empty.access(0)


def test_wavelet_rejects_bad_index():
    tree = WaveletTree(b"ab")
    with pytest.raises(IndexError):
        tree.access(2)
    with pytest.raises(ValueError):
        tree.rank(300, 1)
