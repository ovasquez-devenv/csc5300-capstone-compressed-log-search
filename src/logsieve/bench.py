"""Timing harness for the Week 14 LogSieve experiments.

Wall time comes from time.perf_counter. Garbage collection is turned off
during a timed call and forced once before the repeats, which is the
protocol in Amakobe section 14.3. Each configuration is repeated so the
tables can show the mean, the sample standard deviation, the median, and
the interquartile range. Pattern draws and the Count-Min hash use a fixed seed.

The default sizes stay in the range a normal Windows PC can finish in a few
minutes. Pass quick=True for a smoke test.
"""

from __future__ import annotations

import csv
import gc
import json
import logging
import os
import platform
import random
import subprocess
import sys
import tarfile
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from logsieve.baselines import (
    AhoCorasick,
    find_count,
    kmp_count,
    naive_count,
    naive_search,
)
from logsieve.fm_index import FMIndex
from logsieve.ingest import SENTINEL, log_from_lines
from logsieve.sketch import CountMinSketch, exact_ip_counts, ipv4_addresses
from logsieve.suffix_array import (
    build_suffix_array,
    suffix_array_count,
    suffix_array_search,
)

logger = logging.getLogger(__name__)

SEED = 5300
WARMUP = 1
ANALYST_TEXT = (
    b"Failed password",
    b"Invalid user",
    b"authentication failure",
    b"error",
    b"Accepted",
)
ABSENT = b"zzqxvnotpresent"

FULL = {
    "line_counts": (2000, 10000, 50000),
    "pattern_lengths": (4, 8, 16, 32, 64),
    "sample_rates": (4, 8, 16, 32, 64),
    "watch_sizes": (10, 50, 100),
    "sketch_widths": (16, 64, 256, 1024),
}
QUICK = {
    "line_counts": (40, 100),
    "pattern_lengths": (4, 8),
    "sample_rates": (4, 8),
    "watch_sizes": (5,),
    "sketch_widths": (16, 64),
}


def repo_root() -> Path:
    """Directory that holds data/sample, whether that is cwd or this repo."""

    candidates = [Path.cwd(), Path(__file__).resolve().parents[2]]
    for candidate in candidates:
        sample = candidate / "data" / "sample" / "OpenSSH_2k.log"
        if sample.exists():
            return candidate
    return Path.cwd()


def capture_environment(root: Path, seed: int, repeats: int, quick: bool) -> dict:
    """Record the machine and the run settings. Missing fields stay null."""

    cpu = None
    ram_bytes = None
    cpuinfo = Path("/proc/cpuinfo")
    meminfo = Path("/proc/meminfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text(errors="replace").splitlines():
            if line.lower().startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    if meminfo.exists():
        for line in meminfo.read_text(errors="replace").splitlines():
            if line.startswith("MemTotal"):
                ram_bytes = int(line.split()[1]) * 1024
                break
    commit = None
    dirty = None
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        dirty = bool(status.strip())
    except (OSError, subprocess.CalledProcessError):
        commit = None
        dirty = None
    return {
        "python": sys.version,
        "python_version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "os": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu": cpu,
        "cpu_count": os.cpu_count(),
        "ram_bytes": ram_bytes,
        "hostname": platform.node(),
        "numpy": np.__version__,
        "git_commit": commit,
        "git_dirty": dirty,
        "seed": seed,
        "repeats": repeats,
        "warmup": WARMUP,
        "gc_disabled_during_timed_sections": True,
        "quick": quick,
        "clock": "time.perf_counter",
    }


def _repeat(fn, repeats: int):
    """Warm up, then time ``repeats`` calls with the collector disabled."""

    gc.collect()
    gc.disable()
    try:
        for _ in range(WARMUP):
            fn()
        times = []
        results = []
        for _ in range(repeats):
            start = time.perf_counter()
            results.append(fn())
            times.append(time.perf_counter() - start)
        return times, results
    finally:
        gc.enable()


def _summary(samples: list[float]) -> dict[str, float]:
    arr = np.asarray(samples, dtype=float)
    std = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
    return {
        "mean_seconds": float(arr.mean()),
        "std_seconds": std,
        "median_seconds": float(np.median(arr)),
        "iqr_seconds": float(np.percentile(arr, 75) - np.percentile(arr, 25)),
    }


def _python_list_bytes(values: np.ndarray) -> int:
    """Bytes of a Python list of the suffix-array integers, objects included."""

    listed = values.tolist()
    total = sys.getsizeof(listed)
    for item in listed:
        total += sys.getsizeof(item)
    return total


def _ensure_openssh(root: Path) -> Path:
    """Prefer the full OpenSSH log, and fall back to the committed 2k sample."""

    sample = root / "data" / "sample" / "OpenSSH_2k.log"
    raw = root / "data" / "raw" / "SSH.log"
    archive = root / "data" / "raw" / "SSH.tar.gz"
    if raw.exists():
        return raw
    if archive.exists():
        logger.info("extracting %s", archive)
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extract("SSH.log", path=root / "data" / "raw")
        if raw.exists():
            return raw
    return sample


def _read_lines(path: Path, max_lines: int) -> list[bytes]:
    lines: list[bytes] = []
    with path.open("rb") as handle:
        for raw in handle:
            if raw.endswith(b"\n"):
                raw = raw[:-1]
            if raw.endswith(b"\r"):
                raw = raw[:-1]
            if SENTINEL in raw:
                raise ValueError("sentinel byte found in %s" % path)
            lines.append(raw)
            if len(lines) >= max_lines:
                break
    if not lines:
        raise ValueError("no lines in %s" % path)
    return lines


def _pattern_text(pattern: bytes) -> str:
    return pattern.decode("utf-8", errors="backslashreplace")


def _workload(body: bytes, lines: list[bytes], lengths: tuple[int, ...], seed: int) -> list[tuple[str, bytes]]:
    """Patterns as (kind, bytes). Kinds are absent, analyst, ip, and random."""

    rng = random.Random(seed)
    patterns: list[tuple[str, bytes]] = [("absent", ABSENT)]
    for text in ANALYST_TEXT:
        patterns.append(("analyst", text))
    addresses: list[bytes] = []
    for line in lines:
        addresses.extend(ipv4_addresses(line))
        if addresses:
            break
    if addresses:
        patterns.append(("ip", addresses[0]))
        parts = addresses[0].split(b".")
        if len(parts) == 4:
            patterns.append(("ip", b".".join(parts[:3]) + b"."))
    n = len(body)
    for length in lengths:
        if length <= 0 or length > n:
            continue
        start = rng.randrange(0, n - length + 1)
        patterns.append(("random", body[start : start + length]))
    seen: set[bytes] = set()
    unique: list[tuple[str, bytes]] = []
    for kind, pattern in patterns:
        if pattern not in seen:
            seen.add(pattern)
            unique.append((kind, pattern))
    return unique


def _check_counts(text: bytes, index: FMIndex, sa: np.ndarray, patterns: list[tuple[str, bytes]]) -> None:
    """Refuse to time a method that disagrees with the naive scan."""

    for _kind, pattern in patterns:
        naive_hits = naive_count(text, pattern)
        others = {
            "kmp": kmp_count(text, pattern),
            "find": find_count(text, pattern),
            "sa": suffix_array_count(text, sa, pattern),
            "fm": index.count(pattern),
        }
        for name, count in others.items():
            if count != naive_hits:
                raise AssertionError(
                    "%s count %d != naive %d for %r" % (name, count, naive_hits, pattern)
                )
        if naive_hits <= 30:
            located = index.locate(pattern)
            scanned = naive_search(text, pattern)
            if located != scanned:
                raise AssertionError("fm locate disagrees with naive for %r" % (pattern,))
            if suffix_array_search(text, sa, pattern) != scanned:
                raise AssertionError("suffix array locate disagrees for %r" % (pattern,))


def _append_trials(
    rows,
    experiment,
    method,
    lines,
    text_bytes,
    pattern,
    sample_rate,
    seed,
    times,
    matches,
    pattern_kind="",
):
    for trial, seconds in enumerate(times, start=1):
        rows.append(
            {
                "experiment": experiment,
                "method": method,
                "lines": lines,
                "text_bytes": text_bytes,
                "pattern": _pattern_text(pattern),
                "pattern_kind": pattern_kind,
                "pattern_len": len(pattern),
                "sample_rate": sample_rate,
                "trial": trial,
                "seconds": seconds,
                "matches": matches,
                "seed": seed,
            }
        )


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _group_summary(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, list[float]] = defaultdict(list)
    meta: dict[tuple, dict] = {}
    for row in rows:
        key = (
            row["experiment"],
            row["method"],
            row["lines"],
            row["pattern"],
            row["sample_rate"],
        )
        groups[key].append(float(row["seconds"]))
        meta[key] = row
    summary = []
    for key, samples in groups.items():
        stats = _summary(samples)
        base = meta[key]
        summary.append(
            {
                "experiment": key[0],
                "method": key[1],
                "lines": key[2],
                "text_bytes": base["text_bytes"],
                "pattern": key[3],
                "pattern_kind": base.get("pattern_kind", ""),
                "pattern_len": base["pattern_len"],
                "sample_rate": key[4],
                "trials": len(samples),
                "matches": base["matches"],
                "seed": base["seed"],
                **stats,
            }
        )
    return summary


def _synthetic(n_body: int, seed: int):
    rng = random.Random(seed)
    alphabet = b"abcdefghijklmnopqrstuvwxyz0123456789 .:/"
    # One line, same byte length as the log body, then the usual sentinel.
    body = bytes(alphabet[rng.randrange(len(alphabet))] for _ in range(n_body))
    return log_from_lines([body], source="synthetic")


def _space_row(dataset: str, log, index: FMIndex, sa: np.ndarray, sa_python: int) -> dict:
    parts = index.component_bytes()
    n = len(log.text)
    return {
        "dataset": dataset,
        "lines": log.line_count,
        "text_bytes": n,
        "raw_body_bytes": len(log.body),
        "sa_numpy_bytes": int(sa.nbytes),
        "sa_python_bytes": sa_python,
        "bwt_bytes": parts["bwt_bytes"],
        "wavelet_packed_bytes": parts["wavelet_packed_bytes"],
        "rank_directory_bytes": parts["rank_directory_bytes"],
        "wavelet_bytes": parts["wavelet_bytes"],
        "wavelet_bits": parts["wavelet_bits"],
        "bits_per_char": (parts["wavelet_bits"] / n) if n else 0,
        "sample_bytes": parts["sample_bytes"],
        "sample_count": parts["sample_count"],
        "c_table_bytes": parts["c_table_bytes"],
        "fm_index_bytes": parts["fm_index_bytes"],
        "fm_without_raw_bwt_bytes": parts["fm_without_raw_bwt_bytes"],
        "sample_rate": index.sample_rate,
        "distinct_symbols": int(len(np.unique(np.frombuffer(log.text, dtype=np.uint8)))),
    }


def _breakeven(summary_rows: list[dict]) -> list[dict]:
    """How many count queries pay for the build, if the index is faster per query."""

    build = {}
    scans = defaultdict(list)
    indexes = defaultdict(list)
    for row in summary_rows:
        if row["experiment"] == "e1_build" and row["method"] == "fm_total":
            build[row["lines"]] = row
        elif row["experiment"] == "e3_count" and row["method"] == "str_find":
            scans[row["lines"]].append(row["median_seconds"])
        elif row["experiment"] == "e3_count" and row["method"] == "fm_count":
            indexes[row["lines"]].append(row["median_seconds"])
    out = []
    for lines, built in build.items():
        if not scans[lines] or not indexes[lines]:
            continue
        scan = float(np.median(scans[lines]))
        indexed = float(np.median(indexes[lines]))
        gap = scan - indexed
        if gap > 0:
            queries = built["median_seconds"] / gap
            status = "index_faster_per_query"
        else:
            queries = None
            status = "index_not_faster_per_query"
        out.append(
            {
                "lines": lines,
                "text_bytes": built["text_bytes"],
                "build_median_seconds": built["median_seconds"],
                "str_find_median_seconds": scan,
                "fm_count_median_seconds": indexed,
                "queries_to_break_even": queries if queries is not None else "",
                "status": status,
            }
        )
    return out


def _slopes(summary_rows: list[dict]) -> dict:
    points = [
        (row["text_bytes"], row["median_seconds"])
        for row in summary_rows
        if row["experiment"] == "e1_build" and row["method"] == "fm_total" and row["median_seconds"] > 0
    ]
    if len(points) < 2:
        return {}
    sizes = np.array([p[0] for p in points], dtype=float)
    times = np.array([p[1] for p in points], dtype=float)
    slope, intercept = np.polyfit(np.log(sizes), np.log(times), 1)
    return {
        "fm_total_loglog_slope": float(slope),
        "fm_total_loglog_intercept": float(intercept),
        "points": [{"text_bytes": int(s), "median_seconds": float(t)} for s, t in points],
    }


def _charts(
    out: Path,
    summary_rows: list[dict],
    space_rows: list[dict],
    sketch_rows: list[dict],
    sample_rows: list[dict],
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    written = []

    def save(fig, name: str) -> None:
        path = out / name
        fig.tight_layout()
        fig.savefig(path, dpi=140)
        plt.close(fig)
        written.append(str(path))

    build_rows = [r for r in summary_rows if r["experiment"] == "e1_build"]
    if build_rows:
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for method in ("suffix_array", "bwt", "wavelet", "fm_total"):
            subset = sorted(
                (r for r in build_rows if r["method"] == method),
                key=lambda r: r["text_bytes"],
            )
            if not subset:
                continue
            ax.plot(
                [r["text_bytes"] for r in subset],
                [r["median_seconds"] for r in subset],
                marker="o",
                label=method,
            )
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("text bytes")
        ax.set_ylabel("median build seconds")
        ax.set_title("E1 build time")
        ax.legend()
        save(fig, "e1_build_time.png")

    if space_rows:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        labels = []
        raw, sa_np, fm = [], [], []
        plotted = [r for r in space_rows if r["dataset"] in ("openssh", "synthetic", "linux")]
        for row in plotted:
            labels.append("%s %d" % (row["dataset"], row["lines"]))
            raw.append(row["text_bytes"])
            sa_np.append(row["sa_numpy_bytes"])
            fm.append(row["fm_index_bytes"])
        xpos = np.arange(len(labels))
        width = 0.25
        ax.bar(xpos - width, raw, width, label="text bytes")
        ax.bar(xpos, sa_np, width, label="suffix array int32")
        ax.bar(xpos + width, fm, width, label="FM-index bytes")
        ax.set_xticks(xpos, labels, rotation=30, ha="right")
        ax.set_ylabel("bytes")
        ax.set_title("E2 space")
        ax.legend()
        save(fig, "e2_space.png")

    count_rows = [r for r in summary_rows if r["experiment"] == "e3_count"]
    length8 = [r for r in count_rows if r["pattern_kind"] == "random" and r["pattern_len"] == 8]
    # Prefer the random length-8 slice over a short analyst query that happens to be length 8.
    if length8:
        fig, ax = plt.subplots(figsize=(7, 4.5))
        methods = []
        for row in length8:
            if row["method"] not in methods:
                methods.append(row["method"])
        for method in methods:
            subset = sorted((r for r in length8 if r["method"] == method), key=lambda r: r["lines"])
            ax.plot(
                [r["lines"] for r in subset],
                [r["median_seconds"] for r in subset],
                marker="o",
                label=method,
            )
        ax.set_xlabel("log lines")
        ax.set_ylabel("median seconds")
        ax.set_title("E3 count latency, pattern length 8")
        ax.legend()
        save(fig, "e3_latency_vs_size.png")

        largest = max(r["lines"] for r in count_rows)
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for method in methods:
            subset = [
                r
                for r in count_rows
                if r["method"] == method and r["lines"] == largest and r["pattern_kind"] == "random"
            ]
            # One point per length: the random slice, which is the only non-analyst of that length
            # unless an IP has the same length. Average medians at each length.
            by_len = defaultdict(list)
            for row in subset:
                by_len[row["pattern_len"]].append(row["median_seconds"])
            if not by_len:
                continue
            lengths = sorted(by_len)
            ax.plot(lengths, [float(np.median(by_len[n])) for n in lengths], marker="o", label=method)
        ax.set_xlabel("pattern length (bytes)")
        ax.set_ylabel("median seconds")
        ax.set_title("E3 count latency by pattern length, %d lines" % largest)
        ax.legend()
        save(fig, "e3_latency_vs_length.png")

    locate_rows = [r for r in summary_rows if r["experiment"] == "e4_locate"]
    if locate_rows:
        fig, ax = plt.subplots(figsize=(7, 4.5))
        subset = sorted(locate_rows, key=lambda r: r["sample_rate"])
        ax.plot(
            [r["sample_rate"] for r in subset],
            [r["median_seconds"] for r in subset],
            marker="o",
            color="tab:blue",
            label="median locate seconds",
        )
        ax.set_xlabel("suffix array sample rate k")
        ax.set_ylabel("median locate seconds")
        memory = {r["sample_rate"]: r["sample_bytes"] for r in sample_rows}
        if memory:
            ax2 = ax.twinx()
            ax2.plot(
                [r["sample_rate"] for r in subset],
                [memory[r["sample_rate"]] for r in subset],
                marker="s",
                color="tab:orange",
                label="sample bytes",
            )
            ax2.set_ylabel("suffix array sample bytes")
            lines_a, labels_a = ax.get_legend_handles_labels()
            lines_b, labels_b = ax2.get_legend_handles_labels()
            ax.legend(lines_a + lines_b, labels_a + labels_b, loc="best")
        else:
            ax.legend()
        ax.set_title("E4 locate time and sample bytes versus k")
        save(fig, "e4_sample_tradeoff.png")

    watch_rows = [r for r in summary_rows if r["experiment"] == "e5_watch"]
    if watch_rows:
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for method in ("aho_corasick", "kmp_repeated", "fm_repeated"):
            subset = sorted((r for r in watch_rows if r["method"] == method), key=lambda r: r["matches"])
            if not subset:
                continue
            ax.plot(
                [r["matches"] for r in subset],
                [r["median_seconds"] for r in subset],
                marker="o",
                label=method,
            )
        ax.set_xlabel("patterns in the watch list")
        ax.set_ylabel("median seconds")
        ax.set_title("E5 many patterns")
        ax.legend()
        save(fig, "e5_many_patterns.png")

    if sketch_rows:
        fig, ax = plt.subplots(figsize=(7, 4.5))
        subset = sorted(sketch_rows, key=lambda r: r["width"])
        ax.plot([r["width"] for r in subset], [r["max_overestimate"] for r in subset], marker="o")
        ax.set_xlabel("sketch width")
        ax.set_ylabel("max overestimate (counts)")
        ax.set_title("E6 Count-Min max error versus width")
        save(fig, "e6_sketch_error.png")
    return written


def run_week14(
    seed: int = SEED,
    repeats: int = 5,
    quick: bool = False,
    output_dir: str | Path = "results",
    line_counts: tuple[int, ...] | None = None,
) -> dict:
    """Run the Week 14 measurements and write CSV, JSON, and PNG files."""

    if repeats < 1:
        raise ValueError("repeats must be >= 1")
    config = dict(QUICK if quick else FULL)
    if line_counts is not None:
        config["line_counts"] = tuple(line_counts)
    root = repo_root()
    out = Path(output_dir)
    if not out.is_absolute():
        out = root / out
    out.mkdir(parents=True, exist_ok=True)
    env = capture_environment(root, seed, repeats, quick)
    source = _ensure_openssh(root)
    env["openssh_source"] = str(source)
    env["line_counts"] = list(config["line_counts"])
    logger.info("benchmark source %s sizes %s repeats %d", source, config["line_counts"], repeats)

    timing_rows: list[dict] = []
    space_rows: list[dict] = []
    sketch_rows: list[dict] = []
    linux_path = root / "data" / "sample" / "Linux_2k.log"

    for lines_wanted in config["line_counts"]:
        lines = _read_lines(source, lines_wanted)
        log = log_from_lines(lines, source=str(source))
        text = log.text
        logger.info("size %d lines, %d bytes", log.line_count, len(text))
        workload = _workload(
            log.body,
            lines,
            config["pattern_lengths"],
            seed + log.line_count,
        )
        sa = build_suffix_array(text)
        holder: dict = {}

        def build(sample_rate: int = 16):
            holder["index"] = FMIndex(text, sample_rate=sample_rate)
            return holder["index"].timings

        # Correctness uses one build that is not part of the timed sample.
        probe = FMIndex(text, sample_rate=16)
        _check_counts(text, probe, sa, workload)
        logger.info("correctness ok for %d lines (%d patterns)", log.line_count, len(workload))

        _times, timed_builds = _repeat(lambda: build(16), repeats)
        index = holder["index"]
        phase_times: dict[str, list[float]] = defaultdict(list)
        for timings in timed_builds:
            phase_times["suffix_array"].append(timings.suffix_array)
            phase_times["bwt"].append(timings.bwt)
            phase_times["wavelet"].append(timings.wavelet)
            phase_times["samples"].append(timings.samples)
            phase_times["fm_total"].append(timings.total)
        for method, samples in phase_times.items():
            _append_trials(
                timing_rows,
                "e1_build",
                method,
                log.line_count,
                len(text),
                b"",
                16,
                seed,
                samples,
                0,
                pattern_kind="build",
            )
        sa_python = _python_list_bytes(sa)
        space_rows.append(_space_row("openssh", log, index, sa, sa_python))
        synthetic = _synthetic(len(log.body), seed + 17)
        syn_sa = build_suffix_array(synthetic.text)
        syn_index = FMIndex(synthetic.text, sample_rate=16)
        space_rows.append(
            _space_row("synthetic", synthetic, syn_index, syn_sa, _python_list_bytes(syn_sa))
        )

        counters = {
            "fm_count": lambda pattern, index=index: index.count(pattern),
            "naive": lambda pattern, text=text: naive_count(text, pattern),
            "kmp": lambda pattern, text=text: kmp_count(text, pattern),
            "str_find": lambda pattern, text=text: find_count(text, pattern),
            "sa_binary": lambda pattern, text=text, sa=sa: suffix_array_count(text, sa, pattern),
        }
        for kind, pattern in workload:
            matches = index.count(pattern)
            for method, fn in counters.items():
                samples, _ = _repeat(lambda fn=fn, pattern=pattern: fn(pattern), repeats)
                _append_trials(
                    timing_rows,
                    "e3_count",
                    method,
                    log.line_count,
                    len(text),
                    pattern,
                    16,
                    seed,
                    samples,
                    matches,
                    pattern_kind=kind,
                )
        logger.info("finished queries for %d lines", log.line_count)

    # E4 and E5 stay on the 2,000 line prefix (or the largest quick prefix).
    # Rebuilding the full 50,000 line index once per sample rate is Week 15 work.
    e4_lines = 2000 if 2000 in set(config["line_counts"]) else config["line_counts"][0]
    e4_source_lines = _read_lines(source, e4_lines)
    e4_log = log_from_lines(e4_source_lines, source=str(source))
    e4_patterns = _workload(e4_log.body, e4_source_lines, (8,), seed + e4_log.line_count)
    locate_pattern = e4_patterns[-1][1]
    locate_kind = e4_patterns[-1][0]
    # Prefer the busiest pattern that still has at most 80 hits. One hit is
    # too small to see the sample-rate walk, and a very common string spends
    # its time in the output list rather than in the walk.
    probe = FMIndex(e4_log.text, sample_rate=8)
    best_hits = -1
    for kind, candidate in e4_patterns:
        hits = probe.count(candidate)
        if 0 < hits <= 80 and hits > best_hits:
            locate_pattern = candidate
            locate_kind = kind
            best_hits = hits
    sample_rows: list[dict] = []
    for rate in config["sample_rates"]:
        index = FMIndex(e4_log.text, sample_rate=rate)
        matches = index.count(locate_pattern)

        def locate(index=index, pattern=locate_pattern):
            return index.locate(pattern)

        samples, _ = _repeat(locate, repeats)
        _append_trials(
            timing_rows,
            "e4_locate",
            "fm_locate",
            e4_log.line_count,
            len(e4_log.text),
            locate_pattern,
            rate,
            seed,
            samples,
            matches,
            pattern_kind=locate_kind,
        )
        parts = index.component_bytes()
        sample_rows.append(
            {
                "lines": e4_log.line_count,
                "text_bytes": len(e4_log.text),
                "sample_rate": rate,
                "matches": matches,
                "pattern": _pattern_text(locate_pattern),
                "sample_bytes": parts["sample_bytes"],
                "sample_count": parts["sample_count"],
                "fm_index_bytes": parts["fm_index_bytes"],
                "fm_without_raw_bwt_bytes": parts["fm_without_raw_bwt_bytes"],
            }
        )

    watch_pool = []
    rng = random.Random(seed + 99)
    body = e4_log.body
    while len(watch_pool) < max(config["watch_sizes"]):
        length = 8 if len(body) >= 8 else max(1, len(body) // 2)
        start = rng.randrange(0, len(body) - length + 1)
        piece = body[start : start + length]
        if piece and piece not in watch_pool:
            watch_pool.append(piece)
    watch_index = FMIndex(e4_log.text, sample_rate=16)
    for width in config["watch_sizes"]:
        patterns = watch_pool[:width]
        auto = AhoCorasick(patterns)

        def run_aho(auto=auto, text=e4_log.text):
            return auto.search(text)

        def run_kmp(patterns=patterns, text=e4_log.text):
            return sum(kmp_count(text, pattern) for pattern in patterns)

        def run_fm(patterns=patterns, index=watch_index):
            return sum(index.count(pattern) for pattern in patterns)

        for method, fn in (
            ("aho_corasick", run_aho),
            ("kmp_repeated", run_kmp),
            ("fm_repeated", run_fm),
        ):
            samples, _ = _repeat(fn, repeats)
            _append_trials(
                timing_rows,
                "e5_watch",
                method,
                e4_log.line_count,
                len(e4_log.text),
                b"%d patterns" % width,
                16,
                seed,
                samples,
                width,
                pattern_kind="watch",
            )

    sketch_lines = _read_lines(source, config["line_counts"][-1])
    exact = exact_ip_counts(sketch_lines)
    exact_bytes = sys.getsizeof(exact)
    for key, value in exact.items():
        exact_bytes += sys.getsizeof(key) + sys.getsizeof(value)
    addresses = list(exact.keys())
    for width in config["sketch_widths"]:
        sketch = CountMinSketch(width=width, depth=4, seed=seed)
        for line in sketch_lines:
            for address in ipv4_addresses(line):
                sketch.update(address)
        if addresses:
            errors = [sketch.query(address) - exact[address] for address in addresses]
            max_error = int(max(errors))
            mean_error = float(sum(errors) / len(errors))
        else:
            max_error = 0
            mean_error = 0.0
        sketch_rows.append(
            {
                "lines": len(sketch_lines),
                "distinct_ips": len(addresses),
                "total_updates": sketch.total,
                "width": width,
                "depth": sketch.depth,
                "seed": seed,
                "max_overestimate": max_error,
                "mean_overestimate": mean_error,
                "sketch_bytes": sketch.nbytes(),
                "exact_counter_bytes": exact_bytes,
            }
        )

    if linux_path.exists() and not quick:
        linux_lines = _read_lines(linux_path, 2000)
        linux_log = log_from_lines(linux_lines, source=str(linux_path))
        linux_sa = build_suffix_array(linux_log.text)
        linux_index = FMIndex(linux_log.text, sample_rate=16)
        space_rows.append(
            _space_row("linux", linux_log, linux_index, linux_sa, _python_list_bytes(linux_sa))
        )

    # The E4 rows carry an extra note key. Drop it for the CSV field set by
    # writing those columns explicitly below if needed. DictWriter uses the
    # first row's keys, so a later note would be dropped. Keep the note off
    # the row to avoid that.
    for row in space_rows:
        row.pop("note", None)

    summary_rows = _group_summary(timing_rows)
    breakeven_rows = _breakeven(summary_rows)
    slopes = _slopes(summary_rows)
    env["loglog_fit"] = slopes
    env["e4_lines"] = e4_log.line_count
    env["locate_pattern"] = _pattern_text(locate_pattern)

    timing_csv = out / "early_benchmarks.csv"
    summary_csv = out / "early_benchmarks_summary.csv"
    space_csv = out / "space_measurements.csv"
    sketch_csv = out / "sketch_measurements.csv"
    breakeven_csv = out / "breakeven.csv"
    env_path = out / "environment.json"
    _write_csv(timing_csv, timing_rows)
    _write_csv(summary_csv, summary_rows)
    _write_csv(space_csv, space_rows)
    sample_csv = out / "sample_rate_memory.csv"
    _write_csv(sketch_csv, sketch_rows)
    _write_csv(sample_csv, sample_rows)
    _write_csv(breakeven_csv, breakeven_rows)
    env_path.write_text(json.dumps(env, indent=2) + "\n")
    charts = _charts(out, summary_rows, space_rows, sketch_rows, sample_rows)
    logger.info("wrote results to %s", out)
    return {
        "timing_csv": str(timing_csv),
        "summary_csv": str(summary_csv),
        "space_csv": str(space_csv),
        "environment_json": str(env_path),
        "charts": charts,
        "slopes": slopes,
        "breakeven": breakeven_rows,
    }
