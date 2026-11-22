"""Load a log file into one byte string plus a line-offset table.

Complexity: reading and normalizing a file of n bytes and L lines is O(n).
Mapping a text position to a line number is O(log L) with binary search.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

# A byte that does not occur in the log. The suffix array needs every suffix
# to be unique, and a trailing sentinel is the usual way to get that.
SENTINEL = 0


def as_bytes(value: str | bytes) -> bytes:
    """Encode a pattern or a small text as bytes.

    str values are UTF-8. bytes values are kept as they are. Anything else
    raises TypeError. The sentinel byte is allowed here; callers that build
    an index reject it in the log body.
    """

    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    raise TypeError("expected str or bytes, got %s" % type(value).__name__)


@dataclass
class LogText:
    """One normalized log and the table that maps a byte offset to a line.

    ``text`` is the lines joined with ``\\n`` and a single sentinel byte
    appended. ``line_starts`` holds the start offset of each line in ``text``.
    Line numbers reported to callers are 1-based.
    """

    text: bytes
    line_starts: np.ndarray
    lines: tuple[bytes, ...]
    source: str

    @property
    def line_count(self) -> int:
        return len(self.lines)

    @property
    def body(self) -> bytes:
        """The joined lines without the sentinel byte."""

        if self.text.endswith(bytes([SENTINEL])):
            return self.text[:-1]
        return self.text

    def line_for_position(self, pos: int) -> tuple[int, bytes]:
        """Return the 1-based line number and the line that contains ``pos``.

        The sentinel maps to the last line. Complexity is O(log L).
        """

        if not self.lines:
            raise ValueError("log has no lines")
        if pos < 0:
            raise ValueError("position must be >= 0")
        idx = int(np.searchsorted(self.line_starts, pos, side="right") - 1)
        if idx < 0:
            idx = 0
        if idx >= len(self.lines):
            idx = len(self.lines) - 1
        return idx + 1, self.lines[idx]


def load_log(path: str | Path, max_lines: int | None = None) -> LogText:
    """Read a log, strip each line ending, and append the sentinel.

    ``max_lines`` keeps a prefix. That is how the benchmarks grow the input
    without indexing a whole multi-megabyte file on every trial. Complexity
    is O(n) in the number of bytes read.

    Raises ValueError if the sentinel byte 0x00 appears in the file, or if
    the file has no lines.
    """

    path = Path(path)
    lines: list[bytes] = []
    with path.open("rb") as handle:
        for raw in handle:
            if raw.endswith(b"\n"):
                raw = raw[:-1]
            if raw.endswith(b"\r"):
                raw = raw[:-1]
            if SENTINEL in raw:
                raise ValueError(
                    "log %s contains the reserved sentinel byte 0x00; "
                    "LogSieve needs that byte for the end marker" % path
                )
            lines.append(raw)
            if max_lines is not None and len(lines) >= max_lines:
                break
    if not lines:
        raise ValueError("log %s has no lines" % path)
    return log_from_lines(lines, source=str(path))


def log_from_lines(lines: list[bytes] | tuple[bytes, ...], source: str = "<memory>") -> LogText:
    """Build a LogText from lines that are already split.

    The joined body uses a single ``\\n`` between lines and does not add a
    trailing newline before the sentinel. Complexity is O(n).
    """

    if not lines:
        raise ValueError("log has no lines")
    cleaned: list[bytes] = []
    for line in lines:
        raw = as_bytes(line) if not isinstance(line, bytes) else line
        if raw.endswith(b"\n"):
            raw = raw[:-1]
        if SENTINEL in raw:
            raise ValueError(
                "a log line contains the reserved sentinel byte 0x00"
            )
        cleaned.append(raw)
    body = b"\n".join(cleaned)
    text = body + bytes([SENTINEL])
    starts = np.empty(len(cleaned), dtype=np.int64)
    pos = 0
    last = len(cleaned) - 1
    for i, line in enumerate(cleaned):
        starts[i] = pos
        pos += len(line)
        if i != last:
            pos += 1
    if pos != len(body):
        raise RuntimeError("line-offset table does not match the joined text")
    return LogText(
        text=text,
        line_starts=starts,
        lines=tuple(cleaned),
        source=source,
    )
