"""Build an index on the OpenSSH sample and run five analyst queries.

Run from anywhere:

    python examples/quick_demo.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from logsieve.query import LogSieve  # noqa: E402

QUERIES = (
    "Failed password",
    "Invalid user",
    "authentication failure",
    "173.234.31.186",
    "Accepted",
)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    path = ROOT / "data" / "sample" / "OpenSSH_2k.log"
    engine = LogSieve.build(path, sample_rate=16)
    print("lines %d, text bytes %d" % (engine.log.line_count, len(engine.log.text)))
    for query in QUERIES:
        matches = engine.search(query)
        print("query %r count %d" % (query, len(matches)))
        if matches:
            first = matches[0]
            line = first.line.decode("utf-8", errors="replace")
            print("  first line %d: %s" % (first.line_number, line[:160]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
