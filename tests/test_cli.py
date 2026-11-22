"""Command line build and search."""

import json
from pathlib import Path

from logsieve.cli import main


def test_build_and_search(tmp_path: Path, capsys):
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
    monkeypatch.chdir(tmp_path)
    # The harness reads sample logs relative to the repo. Point at them.
    sample = Path("/workspace/data/sample")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "sample").symlink_to(sample)
    code = main(["bench", "--quick", "--repeats", "2", "--seed", "5300"])
    assert code == 0
    env = json.loads((tmp_path / "results" / "environment.json").read_text())
    assert env["seed"] == 5300
    assert (tmp_path / "results" / "early_benchmarks.csv").exists()
