"""Command line for LogSieve.

Examples:
    python -m logsieve.cli build data/sample/OpenSSH_2k.log
    python -m logsieve.cli search "Failed password"
    python -m logsieve.cli bench
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from logsieve.query import LogSieve

DEFAULT_INDEX = Path(".logsieve") / "index.pkl"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="logsieve")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="log debug detail in addition to build steps",
    )
    parser.add_argument(
        "--index",
        default=str(DEFAULT_INDEX),
        help="path of the pickled index (default: .logsieve/index.pkl)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="build an FM-index for a log file")
    build.add_argument("path", help="log file to index")
    build.add_argument("--sample-rate", type=int, default=16, dest="sample_rate")
    build.add_argument(
        "--max-lines",
        type=int,
        default=None,
        dest="max_lines",
        help="index only the first N lines",
    )

    search = sub.add_parser("search", help="search the index built by the last build")
    search.add_argument("pattern", help="substring to find")
    search.add_argument(
        "--limit",
        type=int,
        default=5,
        help="how many distinct matching lines to print",
    )

    bench = sub.add_parser("bench", help="run the Week 14 benchmark and write results/")
    bench.add_argument("--seed", type=int, default=5300)
    bench.add_argument("--repeats", type=int, default=5)
    bench.add_argument(
        "--out",
        "--output-dir",
        dest="output_dir",
        default="results",
        help="directory for the CSV files, charts, and environment.json (default: results/)",
    )
    bench.add_argument(
        "--quick",
        action="store_true",
        help="smaller sizes, for a smoke test of the harness",
    )

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        force=True,
    )
    if args.command == "build":
        return _build(args)
    if args.command == "search":
        return _search(args)
    if args.command == "bench":
        return _bench(args)
    parser.error("unknown command")
    return 2


def _build(args: argparse.Namespace) -> int:
    engine = LogSieve.build(
        args.path,
        sample_rate=args.sample_rate,
        max_lines=args.max_lines,
    )
    engine.save(args.index)
    print(
        "indexed %d lines, %d bytes, in %.3f s"
        % (engine.log.line_count, len(engine.log.text), engine.fm.timings.total)
    )
    print("index: %s" % args.index)
    return 0


def _search(args: argparse.Namespace) -> int:
    path = Path(args.index)
    if not path.exists():
        print(
            "no index at %s. Run: python -m logsieve.cli build <logfile>" % path,
            file=sys.stderr,
        )
        return 1
    engine = LogSieve.load(path)
    matches = engine.search(args.pattern)
    print("pattern: %s" % args.pattern)
    print("count: %d" % len(matches))
    shown = 0
    seen: set[int] = set()
    for match in matches:
        if match.line_number in seen:
            continue
        seen.add(match.line_number)
        text = match.line.decode("utf-8", errors="replace")
        print("line %d: %s" % (match.line_number, text))
        shown += 1
        if shown >= args.limit:
            break
    if len(seen) > shown:
        print("(%d more distinct lines not shown)" % (len(seen) - shown))
    return 0


def _bench(args: argparse.Namespace) -> int:
    from logsieve.bench import run_week14

    summary = run_week14(
        seed=args.seed,
        repeats=args.repeats,
        quick=args.quick,
        output_dir=args.output_dir,
    )
    print("wrote %s" % summary["timing_csv"])
    print("wrote %s" % summary["environment_json"])
    for chart in summary["charts"]:
        print("wrote %s" % chart)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
