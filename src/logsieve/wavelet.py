"""Wavelet tree over a byte string, with rank and select.

A wavelet tree (Amakobe section 12.5.3) stores a sequence so that rank and
access take O(log sigma) time. The bit vectors follow the block-rank layout
I used in CSC 5300 Week 13 (Amakobe section 12.5.2): packed words plus a
sample of the 1-bit count at the start of each block. This file is a fresh
implementation for LogSieve, not a copy of that earlier module.

Space for the bits is one bit per symbol per level actually built. The rank
directory adds a constant number of bytes per block. Select is binary search
on rank, so it is O(log n) rank queries and is not on the FM-index hot path.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# 8 words * 64 bits = 512 bits between rank samples.
BLOCK_WORDS = 8


class RankBitVector:
    """Packed bit vector with a sampled rank directory.

    ``rank1(i)`` is the number of 1-bits in ``bits[0:i]`` (i exclusive).
    ``access(i)`` is the bit at index i. ``select1(k)`` is the 0-based index
    of the k-th 1-bit, with k starting at 1.

    rank and access are O(1) with a short scan of at most ``BLOCK_WORDS``
    words. select1 is O(log n) rank calls.
    """

    def __init__(self, bits: np.ndarray):
        raw = np.ascontiguousarray(bits, dtype=np.uint8)
        if raw.ndim != 1:
            raise ValueError("bit vector must be one-dimensional")
        if raw.size and int(raw.max()) > 1:
            raise ValueError("bit vector values must be 0 or 1")
        self.n = int(raw.shape[0])
        if self.n == 0:
            self.words = np.zeros(0, dtype=np.uint64)
            self.samples = np.zeros(1, dtype=np.int64)
            return
        pad = (64 - (self.n % 64)) % 64
        if pad:
            raw = np.pad(raw, (0, pad))
        packed = raw.astype(np.uint64).reshape(-1, 64)
        shifts = np.arange(64, dtype=np.uint64)
        self.words = np.sum(packed << shifts, axis=1, dtype=np.uint64)
        nwords = int(self.words.shape[0])
        nblocks = (nwords + BLOCK_WORDS - 1) // BLOCK_WORDS
        samples = np.zeros(nblocks + 1, dtype=np.int64)
        pops = np.fromiter(
            (int(word).bit_count() for word in self.words),
            dtype=np.int64,
            count=nwords,
        )
        if nwords:
            cumulative = np.cumsum(pops)
            if nblocks > 1:
                samples[1:nblocks] = cumulative[np.arange(1, nblocks) * BLOCK_WORDS - 1]
            samples[nblocks] = int(cumulative[-1])
        self.samples = samples

    def nbytes(self) -> int:
        """Bytes in the packed words and the rank samples. Excludes the object header."""

        return int(self.words.nbytes + self.samples.nbytes)

    def rank1(self, i: int) -> int:
        if i <= 0 or self.n == 0:
            return 0
        if i > self.n:
            i = self.n
        word = i >> 6
        bit = i & 63
        block = word // BLOCK_WORDS
        base = block * BLOCK_WORDS
        total = int(self.samples[block])
        words = self.words
        for index in range(base, word):
            total += int(words[index]).bit_count()
        if bit:
            mask = (1 << bit) - 1
            total += (int(words[word]) & mask).bit_count()
        return total

    def access(self, i: int) -> int:
        if i < 0 or i >= self.n:
            raise IndexError("bit index %d out of range" % i)
        return (int(self.words[i >> 6]) >> (i & 63)) & 1

    def select1(self, k: int) -> int:
        """Index of the k-th 1-bit. k is 1-based. Raises ValueError if missing."""

        total = self.rank1(self.n)
        if k <= 0 or k > total:
            raise ValueError("select1(%d) but the vector has %d ones" % (k, total))
        lo, hi = 0, self.n
        while lo < hi:
            mid = (lo + hi) // 2
            if self.rank1(mid) >= k:
                hi = mid
            else:
                lo = mid + 1
        return lo - 1

    def rank0(self, i: int) -> int:
        if i <= 0:
            return 0
        if i > self.n:
            i = self.n
        return i - self.rank1(i)


@dataclass
class _Node:
    lo: int
    hi: int
    mid: int = -1
    bv: RankBitVector | None = None
    left: "_Node | None" = None
    right: "_Node | None" = None


class WaveletTree:
    """Balanced wavelet tree on a byte sequence.

    ``rank(symbol, i)`` counts occurrences of ``symbol`` in ``data[0:i]``.
    ``access(i)`` returns the symbol at index i. Both are O(log sigma).
    Building is O(n log sigma) time and the bit vectors hold O(n log sigma) bits.
    Ranges that contain only one distinct symbol collapse to a leaf.
    """

    def __init__(self, data: bytes | np.ndarray):
        if isinstance(data, (bytes, bytearray)):
            array = np.frombuffer(bytes(data), dtype=np.uint8).copy()
        else:
            array = np.ascontiguousarray(data, dtype=np.uint8)
        self.n = int(array.shape[0])
        self.root = _build(array, 0, 255)
        self._bit_count = 0
        self._node_count = 0
        self._directory_bytes = 0
        self._packed_bytes = 0
        self._walk_stats(self.root)

    def _walk_stats(self, node: _Node | None) -> None:
        if node is None:
            return
        self._node_count += 1
        if node.bv is not None:
            self._bit_count += node.bv.n
            self._packed_bytes += int(node.bv.words.nbytes)
            self._directory_bytes += int(node.bv.samples.nbytes)
        self._walk_stats(node.left)
        self._walk_stats(node.right)

    @property
    def bit_count(self) -> int:
        """Number of bit-vector entries. This is the wavelet's theoretical bit cost."""

        return self._bit_count

    @property
    def node_count(self) -> int:
        return self._node_count

    def nbytes(self) -> int:
        """Packed bits plus rank-directory samples."""

        return self._packed_bytes + self._directory_bytes

    def rank(self, symbol: int, i: int) -> int:
        if self.n == 0 or i <= 0:
            return 0
        if not 0 <= symbol <= 255:
            raise ValueError("symbol must be a byte")
        if i > self.n:
            i = self.n
        node = self.root
        while node is not None and node.bv is not None:
            if symbol <= node.mid:
                i = i - node.bv.rank1(i)
                node = node.left
            else:
                i = node.bv.rank1(i)
                node = node.right
        if node is None or symbol != node.lo:
            return 0
        return i

    def access(self, i: int) -> int:
        if i < 0 or i >= self.n:
            raise IndexError("wavelet index %d out of range" % i)
        node = self.root
        while node.bv is not None:
            if node.bv.access(i) == 0:
                i = i - node.bv.rank1(i)
                node = node.left
            else:
                i = node.bv.rank1(i)
                node = node.right
            if node is None:
                raise RuntimeError("wavelet access left the tree")
        return node.lo


def _build(data: np.ndarray, lo: int, hi: int) -> _Node:
    if data.size == 0:
        return _Node(lo=lo, hi=lo)
    vmin = int(data.min())
    vmax = int(data.max())
    if vmin == vmax:
        return _Node(lo=vmin, hi=vmin)
    mid = (vmin + vmax) // 2
    bits = data > mid
    node = _Node(lo=vmin, hi=vmax, mid=mid, bv=RankBitVector(bits))
    left = data[~bits]
    right = data[bits]
    node.left = _build(left, vmin, mid)
    node.right = _build(right, mid + 1, vmax)
    return node
