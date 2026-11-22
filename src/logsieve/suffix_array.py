"""Suffix array by prefix doubling.

The construction follows the prefix-doubling idea in Manber and Myers (1993)
and in Amakobe section 10.5. Each pass sorts suffixes by a pair of ranks that
cover twice as many characters as the pass before it. I sort each pair with
``numpy.lexsort``, so one pass is O(n log n) and the whole build is
O(n log^2 n). A linear-time algorithm exists (Karkkainen, Sanders, and
Burkhardt 2006); that is planned for Week 15, not used here.

The layout is a rewrite of the suffix array I built for CSC 5300 Week 11,
kept in this package so the capstone stands on its own.

Correctness check used in the tests: on small strings the result matches
``sorted(range(n), key=lambda i: text[i:])``.
"""

from __future__ import annotations

import numpy as np


def build_suffix_array(text: bytes) -> np.ndarray:
    """Return the suffix array of ``text`` as ``int32`` positions.

    ``sa[i]`` is the starting position of the i-th suffix in lexicographic
    order. Complexity is O(n log^2 n) time and O(n) extra words.

    The text should end with a unique sentinel if the caller needs every
    suffix to be strictly ordered by content. Identical suffixes stay in a
    deterministic order and share a rank until a later pass splits them.
    """

    if not isinstance(text, (bytes, bytearray)):
        raise TypeError("suffix array text must be bytes")
    n = len(text)
    if n == 0:
        return np.zeros(0, dtype=np.int32)
    if n > np.iinfo(np.int32).max:
        raise ValueError("text longer than int32 can index is not supported")

    rank = np.frombuffer(bytes(text), dtype=np.uint8).astype(np.int32)
    k = 1
    sa = np.arange(n, dtype=np.int32)
    # At most ceil(log2 n) doublings. The cap stops a no-sentinel tie from looping.
    for _ in range(n.bit_length() + 1):
        second = np.full(n, -1, dtype=np.int32)
        if k < n:
            second[: n - k] = rank[k:]
        # lexsort: the last key is the primary key. Order by (rank[i], second[i]).
        sa = np.lexsort((second, rank)).astype(np.int32, copy=False)
        prev = sa[:-1]
        curr = sa[1:]
        differ = (rank[prev] != rank[curr]) | (second[prev] != second[curr])
        change = np.zeros(n, dtype=np.int32)
        change[1:] = differ.astype(np.int32)
        new_rank = np.empty(n, dtype=np.int32)
        new_rank[sa] = np.cumsum(change, dtype=np.int32)
        rank = new_rank
        if int(rank[sa[-1]]) == n - 1:
            break
        k *= 2
        if k >= n and int(rank[sa[-1]]) == n - 1:
            break
    return sa


def naive_suffix_array(text: bytes) -> list[int]:
    """Reference builder, O(n^2 log n) character comparisons. Tests only."""

    return sorted(range(len(text)), key=lambda i: text[i:])


def suffix_array_bounds(text: bytes, sa: np.ndarray, pattern: bytes) -> tuple[int, int]:
    """Half-open range of suffix-array rows whose suffixes start with ``pattern``.

    Two binary searches, O(m log n) character comparisons. An empty pattern
    covers every row. A pattern longer than the text covers nothing.
    """

    if not isinstance(pattern, (bytes, bytearray)):
        raise TypeError("pattern must be bytes")
    n = len(text)
    if pattern == b"":
        return 0, n
    m = len(pattern)
    if m > n:
        return 0, 0
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        if text[int(sa[mid]) : int(sa[mid]) + m] < pattern:
            lo = mid + 1
        else:
            hi = mid
    left = lo
    lo, hi = left, n
    while lo < hi:
        mid = (lo + hi) // 2
        chunk = text[int(sa[mid]) : int(sa[mid]) + m]
        # A hit has the pattern as a prefix of the suffix. A shorter suffix
        # that is only a proper prefix compares as less than the pattern.
        if chunk.startswith(pattern) or chunk < pattern:
            lo = mid + 1
        else:
            hi = mid
    return left, lo


def suffix_array_count(text: bytes, sa: np.ndarray, pattern: bytes) -> int:
    """Number of occurrences. O(m log n), independent of how many hits there are."""

    left, right = suffix_array_bounds(text, sa, pattern)
    return right - left


def suffix_array_search(text: bytes, sa: np.ndarray, pattern: bytes) -> list[int]:
    """Locate ``pattern``. O(m log n + occ) after the suffix array exists.

    An empty pattern is defined as one hit at every text position.
    """

    if pattern == b"":
        return list(range(len(text)))
    left, right = suffix_array_bounds(text, sa, pattern)
    return sorted(int(sa[i]) for i in range(left, right))
