"""LogSieve facade: build an index and return log lines for a pattern.

``build`` reads a file, ``count`` answers how many times a substring occurs,
and ``search`` turns those byte offsets into 1-based line numbers and the
line text. The FM-index does the matching. The line-offset table from ingest
does the mapping, in O(log L) per hit.
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path

from logsieve.fm_index import FMIndex
from logsieve.ingest import LogText, as_bytes, load_log, log_from_lines

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Match:
    """One occurrence of a pattern in the log."""

    line_number: int
    offset: int
    line: bytes


class LogSieve:
    """An immutable index over one normalized log."""

    def __init__(self, log: LogText, sample_rate: int = 16, fm: FMIndex | None = None):
        self.log = log
        self.sample_rate = sample_rate
        if fm is None:
            logger.info(
                "building FM-index for %s (%d lines, %d bytes, sample rate %d)",
                log.source,
                log.line_count,
                len(log.text),
                sample_rate,
            )
            fm = FMIndex(log.text, sample_rate=sample_rate)
            timing = fm.timings
            logger.info(
                "build finished in %.4fs (suffix array %.4fs, BWT %.4fs, wavelet %.4fs, samples %.4fs)",
                timing.total,
                timing.suffix_array,
                timing.bwt,
                timing.wavelet,
                timing.samples,
            )
        self.fm = fm

    @classmethod
    def build(
        cls,
        path: str | Path,
        sample_rate: int = 16,
        max_lines: int | None = None,
    ) -> "LogSieve":
        """Load ``path`` and build the index. O(n log^2 n) for the suffix array."""

        log = load_log(path, max_lines=max_lines)
        return cls(log, sample_rate=sample_rate)

    @classmethod
    def from_lines(
        cls,
        lines: list[bytes] | tuple[bytes, ...],
        sample_rate: int = 16,
        source: str = "<memory>",
    ) -> "LogSieve":
        return cls(log_from_lines(list(lines), source=source), sample_rate=sample_rate)

    def count(self, pattern: str | bytes) -> int:
        """Occurrence count. O(m log sigma)."""

        return self.fm.count(as_bytes(pattern))

    def locate(self, pattern: str | bytes) -> list[int]:
        """Starting byte offsets. O(m log sigma + occ * k * log sigma)."""

        return self.fm.locate(as_bytes(pattern))

    def search(self, pattern: str | bytes) -> list[Match]:
        """Matches with 1-based line numbers and the full line.

        Offsets that land on the sentinel are dropped. Complexity is the
        locate cost plus O(occ log L).
        """

        pattern_bytes = as_bytes(pattern)
        sentinel_at = len(self.log.text) - 1
        matches: list[Match] = []
        for offset in self.fm.locate(pattern_bytes):
            if offset >= sentinel_at and pattern_bytes:
                continue
            line_number, line = self.log.line_for_position(offset)
            matches.append(Match(line_number=line_number, offset=offset, line=line))
        return matches

    def save(self, path: str | Path) -> None:
        """Pickle the index so a later search does not rebuild it."""

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            pickle.dump(self, handle, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info("wrote index to %s", path)

    @classmethod
    def load(cls, path: str | Path) -> "LogSieve":
        path = Path(path)
        with path.open("rb") as handle:
            obj = pickle.load(handle)
        if not isinstance(obj, cls):
            raise TypeError("file %s is not a LogSieve index" % path)
        return obj
