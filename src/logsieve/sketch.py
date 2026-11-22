"""Count-Min sketch for a streaming frequency summary.

Cormode and Muthukrishnan (2005), also Amakobe section 13.4.2.1. The sketch
keeps a width-by-depth table of counters. An update touches one counter in
each row. A query returns the minimum of those counters, which never goes
below the true count. With width about e / epsilon and depth about ln(1 / delta),
the estimate is at most the true count plus epsilon times the stream length,
with probability at least 1 - delta.

This is the Week 14 version of the stretch goal. It is tested against an
exact counter. It is not wired into the search path.
"""

from __future__ import annotations

import math
from collections import Counter

import numpy as np

# FNV-1a 64-bit offset basis and prime. Stable across processes, unlike hash().
_FNV_OFFSET = 14695981039346656037
_FNV_PRIME = 1099511628211


def fnv1a(item: bytes) -> int:
    """64-bit FNV-1a. O(length of item)."""

    if not isinstance(item, (bytes, bytearray)):
        raise TypeError("sketch keys must be bytes")
    value = _FNV_OFFSET
    for symbol in item:
        value ^= symbol
        value = (value * _FNV_PRIME) & 0xFFFFFFFFFFFFFFFF
    return value


class CountMinSketch:
    """Non-negative frequency sketch. Estimates never undercount."""

    def __init__(self, width: int, depth: int, seed: int = 5300):
        if width < 2 or depth < 1:
            raise ValueError("width must be >= 2 and depth must be >= 1")
        self.width = int(width)
        self.depth = int(depth)
        self.seed = int(seed)
        self.table = np.zeros((self.depth, self.width), dtype=np.int64)
        self.total = 0
        rng = np.random.default_rng(self.seed)
        # Odd multipliers keep the family closer to pairwise independent on 2^64.
        self.a = rng.integers(1, 2**31, size=self.depth, dtype=np.int64)
        self.a = self.a * 2 + 1
        self.b = rng.integers(0, 2**31, size=self.depth, dtype=np.int64)

    @classmethod
    def from_error(cls, epsilon: float, delta: float, seed: int = 5300) -> "CountMinSketch":
        """Pick width and depth from the usual epsilon and delta bounds."""

        if not 0 < epsilon < 1:
            raise ValueError("epsilon must be between 0 and 1")
        if not 0 < delta < 1:
            raise ValueError("delta must be between 0 and 1")
        width = max(2, math.ceil(math.e / epsilon))
        depth = max(1, math.ceil(math.log(1.0 / delta)))
        return cls(width, depth, seed=seed)

    def _columns(self, item: bytes) -> list[int]:
        digest = fnv1a(item)
        return [int((int(self.a[i]) * digest + int(self.b[i])) % self.width) for i in range(self.depth)]

    def update(self, item: bytes, count: int = 1) -> None:
        """Add ``count`` to ``item``. O(depth)."""

        if count < 0:
            raise ValueError("Count-Min updates must be non-negative")
        if count == 0:
            return
        for row, column in enumerate(self._columns(item)):
            self.table[row, column] += count
        self.total += count

    def query(self, item: bytes) -> int:
        """Estimated frequency. Always >= the true frequency. O(depth)."""

        columns = self._columns(item)
        return int(min(int(self.table[row, columns[row]]) for row in range(self.depth)))

    def nbytes(self) -> int:
        """Counter table only, not the Python object header."""

        return int(self.table.nbytes)


def ipv4_addresses(line: bytes) -> list[bytes]:
    """Return dotted IPv4 tokens in one log line. O(length of the line)."""

    found: list[bytes] = []
    current = bytearray()
    groups = 0
    digits = 0
    saw_dot = False

    def flush() -> None:
        nonlocal groups, digits, saw_dot
        if groups == 3 and digits > 0 and saw_dot:
            found.append(bytes(current))
        current.clear()
        groups = 0
        digits = 0
        saw_dot = False

    for symbol in line:
        if 48 <= symbol <= 57:  # digit
            if digits >= 3:
                flush()
            current.append(symbol)
            digits += 1
        elif symbol == 46 and digits > 0 and groups < 3:  # dot
            current.append(symbol)
            groups += 1
            digits = 0
            saw_dot = True
        else:
            flush()
    flush()
    return found


def exact_ip_counts(lines: list[bytes] | tuple[bytes, ...]) -> Counter[bytes]:
    """Exact source-address counts. The sketch is measured against this."""

    counts: Counter[bytes] = Counter()
    for line in lines:
        for address in ipv4_addresses(line):
            counts[address] += 1
    return counts
