"""Burrows-Wheeler Transform from a suffix array, and its inverse.

Burrows and Wheeler (1994) reorder a text so the same characters tend to
clump together. Ferragina and Manzini (2000) search that reordered string
without expanding it. Building the transform from the suffix array is O(n).
The inverse used here is the LF mapping, also O(n).
"""

from __future__ import annotations

import numpy as np

from logsieve.suffix_array import build_suffix_array


def burrows_wheeler(text: bytes, sa: np.ndarray | None = None) -> bytes:
    """Return the BWT of ``text``.

    The character at row ``i`` is the character just before the suffix
    ``sa[i]``. The row whose suffix starts at position 0 stores the last
    character of the text. Complexity is O(n) after the suffix array exists.
    """

    if not isinstance(text, (bytes, bytearray)):
        raise TypeError("text must be bytes")
    n = len(text)
    if n == 0:
        return b""
    if sa is None:
        sa = build_suffix_array(text)
    if len(sa) != n:
        raise ValueError("suffix array length does not match the text")
    src = np.frombuffer(bytes(text), dtype=np.uint8)
    prev = sa.astype(np.int64, copy=False) - 1
    prev[prev < 0] = n - 1
    return src[prev].astype(np.uint8, copy=False).tobytes()


def occurrence_counts(bwt: bytes) -> np.ndarray:
    """Return a length-256 array of symbol counts. O(n)."""

    if not bwt:
        return np.zeros(256, dtype=np.int64)
    return np.bincount(np.frombuffer(bwt, dtype=np.uint8), minlength=256).astype(
        np.int64, copy=False
    )


def c_table(bwt: bytes) -> np.ndarray:
    """Return C[c] = number of BWT symbols strictly smaller than c.

    Complexity is O(n + sigma) with sigma fixed at 256.
    """

    counts = occurrence_counts(bwt)
    table = np.zeros(256, dtype=np.int64)
    table[1:] = np.cumsum(counts[:-1])
    return table


def inverse_bwt(bwt: bytes, sentinel: int = 0) -> bytes:
    """Invert a BWT that contains one sentinel byte.

    Complexity is O(n + sigma). Raises ValueError if the sentinel is missing
    or appears more than once, because the start row would be ambiguous.
    """

    if not isinstance(bwt, (bytes, bytearray)):
        raise TypeError("bwt must be bytes")
    n = len(bwt)
    if n == 0:
        return b""
    if not 0 <= sentinel <= 255:
        raise ValueError("sentinel must be a byte value")
    found = [i for i, byte in enumerate(bwt) if byte == sentinel]
    if len(found) != 1:
        raise ValueError(
            "inverse BWT needs exactly one sentinel byte, found %d" % len(found)
        )
    starts = c_table(bwt)
    seen = np.zeros(256, dtype=np.int64)
    lf = np.empty(n, dtype=np.int64)
    for i, byte in enumerate(bwt):
        lf[i] = starts[byte] + seen[byte]
        seen[byte] += 1
    out = bytearray(n)
    idx = found[0]
    for i in range(n - 1, -1, -1):
        out[i] = bwt[idx]
        idx = int(lf[idx])
    return bytes(out)
