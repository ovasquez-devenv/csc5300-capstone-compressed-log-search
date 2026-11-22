"""Command line build and search."""

import hashlib
import json
from pathlib import Path

from logsieve.cli import main

REPO = Path(__file__).resolve().parents[1]


def _fingerprint(directory: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    if not directory.exists():
        return found
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            found[str(path.relative_to(directory))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def test_build_and_search(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.chdir(REPO)
    index = tmp_path / "index.pkl"
    code = main(
        [
            "--index",
            str(index),
            "build",
            "data/sample/synthetic_tiny.log",
            "--sample-rate",
            "4",
        ]
    )
    assert code == 0
    assert index.exists()
    code = main(
        ["--index", str(index), "search", "disk quota", "--limit", "2"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "count: 2" in out
    assert "line " in out


def test_search_without_index(tmp_path: Path, capsys):
    code = main(["--index", str(tmp_path / "missing.pkl"), "search", "x"])
    assert code == 1
    err = capsys.readouterr().err
    assert "no index" in err


def test_quick_bench_writes_csv(tmp_path: Path, monkeypatch):
    sample = REPO / "data" / "sample" / "OpenSSH_2k.log"
    assert sample.is_file()
    out = tmp_path / "bench-out"
    before = _fingerprint(REPO / "results")
    monkeypatch.chdir(REPO)
    code = main(
        [
            "bench",
            "--quick",
            "--repeats",
            "2",
            "--seed",
            "5300",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    assert _fingerprint(REPO / "results") == before
    env = json.loads((out / "environment.json").read_text())
    assert env["seed"] == 5300
    assert not Path(env["openssh_source"]).is_absolute()
    assert (out / "early_benchmarks.csv").is_file()
    assert not (REPO / "results" / "bench-out").exists()
