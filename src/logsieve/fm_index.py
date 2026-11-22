"""FM-index: backward search on the BWT, with a sampled suffix array.

Ferragina and Manzini (2000) count a pattern by walking it right to left.
Each step is one rank on the BWT, which the wavelet tree answers in
O(log sigma). A pattern of length m therefore counts in O(m log sigma).

Locate walks the LF mapping back to a sampled suffix-array row. With sample
rate k the walk is at most k steps, so one occurrence costs O(k log sigma)
and occ occurrences cost O(occ * k * log sigma). Samples are the rows whose
text position is a multiple of k, plus the last position, stored in sorted
arrays rather than a Python dict so the overhead stays close to 8 bytes per
sample.

The full suffix array is dropped after the samples are taken. Count does not
need it, and it is the large part we are trying not to keep.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from logsieve.bwt import burrows_wheeler, c_table
from logsieve.suffix_array import build_suffix_array
from logsieve.wavelet import WaveletTree


@dataclass
class BuildTimings:
    suffix_array: float
    bwt: float
    wavelet: float
    samples: float
    total: float


class FMIndex:
    """Count, locate, and extract on one immutable text."""

    def __init__(self, text: bytes, sample_rate: int = 16):
        if not isinstance(text, (bytes, bytearray)):
            raise TypeError("FM-index text must be bytes")
        if isinstance(sample_rate, bool) or not isinstance(sample_rate, int):
            raise TypeError("sample_rate must be an int")
        if sample_rate < 1:
            raise ValueError("sample_rate must be a positive integer")
        self.text = bytes(text)
        self.n = len(self.text)
        self.sample_rate = sample_rate
        started = time.perf_counter()
        mark = started
        sa = build_suffix_array(self.text)
        sa_seconds = time.perf_counter() - mark
        mark = time.perf_counter()
        transformed = burrows_wheeler(self.text, sa)
        bwt_seconds = time.perf_counter() - mark
        self.bwt = np.frombuffer(transformed, dtype=np.uint8).copy()
        mark = time.perf_counter()
        self.wavelet = WaveletTree(self.bwt)
        wavelet_seconds = time.perf_counter() - mark
        self.C = c_table(transformed)
        mark = time.perf_counter()
        self._store_samples(sa)
        sample_seconds = time.perf_counter() - mark
        # The full suffix array is only a construction scratch array.
        del sa
        self.timings = BuildTimings(
            suffix_array=sa_seconds,
            bwt=bwt_seconds,
            wavelet=wavelet_seconds,
            samples=sample_seconds,
            total=time.perf_counter() - started,
        )

    def _store_samples(self, sa: np.ndarray) -> None:
        k = self.sample_rate
        n = self.n
        rows: list[int] = []
        positions: list[int] = []
        for row, pos in enumerate(sa.tolist()):
            if pos % k == 0 or pos == n - 1:
                rows.append(row)
                positions.append(pos)
        row_arr = np.asarray(rows, dtype=np.int32)
        pos_arr = np.asarray(positions, dtype=np.int32)
        row_order = np.argsort(row_arr, kind="mergesort")
        self.sampled_rows = row_arr[row_order]
        self.sampled_pos_by_row = pos_arr[row_order]
        pos_order = np.argsort(pos_arr, kind="mergesort")
        self.sampled_pos = pos_arr[pos_order]
        self.sampled_row_by_pos = row_arr[pos_order]

    def lf(self, row: int) -> int:
        """LF mapping: row of the suffix that starts one character earlier.

        LF(i) = C[c] + rank(c, i), where c is BWT[i] and rank excludes i.
        One call is O(log sigma) because of the wavelet rank.
        """

        symbol = int(self.bwt[row])
        return int(self.C[symbol] + self.wavelet.rank(symbol, row))

    def _range(self, pattern: bytes) -> tuple[int, int]:
        """Half-open suffix-array range of suffixes that start with pattern."""

        if pattern == b"":
            return 0, self.n
        sp = 0
        ep = self.n
        for symbol in reversed(pattern):
            sp = int(self.C[symbol] + self.wavelet.rank(symbol, sp))
            ep = int(self.C[symbol] + self.wavelet.rank(symbol, ep))
            if sp >= ep:
                return 0, 0
        return sp, ep

    def count(self, pattern: bytes) -> int:
        """Number of occurrences. Empty pattern counts one hit per position.

        Complexity is O(m log sigma), independent of the number of hits.
        """

        if not isinstance(pattern, (bytes, bytearray)):
            raise TypeError("pattern must be bytes")
        sp, ep = self._range(pattern)
        return ep - sp

    def _locate_row(self, row: int) -> int:
        steps = 0
        limit = self.sample_rate + 1
        rows = self.sampled_rows
        while True:
            found = int(np.searchsorted(rows, row))
            if found < len(rows) and int(rows[found]) == row:
                return int(self.sampled_pos_by_row[found]) + steps
            row = self.lf(row)
            steps += 1
            if steps > limit:
                raise RuntimeError("locate walked past the sample rate without a hit")

    def locate(self, pattern: bytes) -> list[int]:
        """Starting positions of ``pattern``, sorted ascending.

        Complexity is O(m log sigma + occ * k * log sigma).
        """

        if not isinstance(pattern, (bytes, bytearray)):
            raise TypeError("pattern must be bytes")
        if pattern == b"":
            return list(range(self.n))
        sp, ep = self._range(pattern)
        positions = [self._locate_row(row) for row in range(sp, ep)]
        positions.sort()
        return positions

    def _row_for_position(self, pos: int) -> int:
        if pos < 0 or pos >= self.n:
            raise ValueError("position %d is outside the text" % pos)
        found = int(np.searchsorted(self.sampled_pos, pos))
        if found >= len(self.sampled_pos):
            raise RuntimeError("no suffix-array sample at or after position %d" % pos)
        sample_pos = int(self.sampled_pos[found])
        row = int(self.sampled_row_by_pos[found])
        for _ in range(sample_pos - pos):
            row = self.lf(row)
        return row

    def extract(self, start: int, end: int) -> bytes:
        """Return ``text[start:end]`` from the index.

        ``end`` is exclusive and must be at most n. The walk starts at the
        next sampled position at or after ``end`` (or at ``end`` when ``end``
        is n, which uses the row of position 0 and the circular BWT) and then
        steps backward. Complexity is O((k + end - start) log sigma).
        """

        if not 0 <= start <= end <= self.n:
            raise ValueError("extract range [%d, %d) is outside [0, %d]" % (start, end, self.n))
        if start == end:
            return b""
        # BWT[row(p)] is text[p - 1], so the row of `end` yields text[end - 1]
        # first. Position n has no row; the row of position 0 stores text[n - 1]
        # and LF then walks back through the end of the text.
        if end == self.n:
            row = self._row_for_position(0)
        else:
            row = self._row_for_position(end)
        chars = bytearray()
        for _ in range(end - start):
            chars.append(int(self.bwt[row]))
            row = self.lf(row)
        chars.reverse()
        return bytes(chars)

    def component_bytes(self) -> dict[str, int]:
        """Measured bytes of each index piece.

        ``fm_index_bytes`` is the wavelet (packed bits and rank samples), the
        C table, the suffix-array samples, and the retained BWT array. The
        original text is not included. ``wavelet_bits`` is the number of
        bit-vector entries, which is the size the tree would have if each
        entry were one bit.
        """

        wavelet_bytes = self.wavelet.nbytes()
        sample_bytes = (
            int(self.sampled_rows.nbytes)
            + int(self.sampled_pos_by_row.nbytes)
            + int(self.sampled_pos.nbytes)
            + int(self.sampled_row_by_pos.nbytes)
        )
        bwt_bytes = int(self.bwt.nbytes)
        c_bytes = int(self.C.nbytes)
        return {
            "bwt_bytes": bwt_bytes,
            "wavelet_bytes": wavelet_bytes,
            "wavelet_packed_bytes": self.wavelet._packed_bytes,
            "rank_directory_bytes": self.wavelet._directory_bytes,
            "wavelet_bits": self.wavelet.bit_count,
            "sample_bytes": sample_bytes,
            "sample_count": int(self.sampled_rows.shape[0]),
            "c_table_bytes": c_bytes,
            "fm_index_bytes": wavelet_bytes + sample_bytes + c_bytes + bwt_bytes,
            "fm_without_raw_bwt_bytes": wavelet_bytes + sample_bytes + c_bytes,
        }
