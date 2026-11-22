"""Log loading, the line-offset table, and the search facade."""

from pathlib import Path

import pytest

from logsieve.ingest import SENTINEL, load_log, log_from_lines
from logsieve.query import LogSieve


def test_join_sentinel_and_line_numbers():
    log = log_from_lines([b"alpha", b"beta", b"gamma"])
    assert log.text == b"alpha\nbeta\ngamma" + bytes([SENTINEL])
    assert log.line_starts.tolist() == [0, 6, 11]
    assert log.line_for_position(0)[0] == 1
    assert log.line_for_position(5)[0] == 1  # the newline sits with the line before it
    assert log.line_for_position(6) == (2, b"beta")
    assert log.line_for_position(len(log.text) - 1)[0] == 3


def test_strips_trailing_newline_and_crlf(tmp_path: Path):
    path = tmp_path / "sample.log"
    path.write_bytes(b"one\r\ntwo\r\n")
    log = load_log(path)
    assert log.lines == (b"one", b"two")
    assert log.text == b"one\ntwo" + bytes([SENTINEL])


def test_openssh_sample_has_two_thousand_lines():
    log = load_log("data/sample/OpenSSH_2k.log")
    assert log.line_count == 2000
    assert log.text.endswith(bytes([SENTINEL]))
    assert SENTINEL not in log.body
    linux = load_log("data/sample/Linux_2k.log")
    assert linux.line_count == 2000


def test_max_lines_prefix():
    log = load_log("data/sample/OpenSSH_2k.log", max_lines=10)
    assert log.line_count == 10
    full = load_log("data/sample/OpenSSH_2k.log")
    assert log.lines == full.lines[:10]


def test_sentinel_in_the_file_is_rejected(tmp_path: Path):
    path = tmp_path / "bad.log"
    path.write_bytes(b"ok\n\x00hidden\n")
    with pytest.raises(ValueError, match="sentinel"):
        load_log(path)


def test_empty_file_is_rejected(tmp_path: Path):
    path = tmp_path / "empty.log"
    path.write_bytes(b"")
    with pytest.raises(ValueError):
        load_log(path)


def test_search_returns_lines_and_matches_naive_count():
    engine = LogSieve.from_lines(
        [
            b"Failed password for root",
            b"ok",
            b"Failed password for ada",
            b"nothing",
        ],
        sample_rate=2,
    )
    assert engine.count("Failed password") == 2
    matches = engine.search("Failed password")
    assert [m.line_number for m in matches] == [1, 3]
    assert matches[0].line == b"Failed password for root"
    assert engine.count("missing") == 0
    assert engine.search("missing") == []


def test_non_ascii_line_search():
    engine = LogSieve.from_lines(["café login".encode(), b"other"], sample_rate=1)
    matches = engine.search("café")
    assert len(matches) == 1
    assert matches[0].line_number == 1


def test_pattern_longer_than_text_and_empty_pattern():
    engine = LogSieve.from_lines([b"short"], sample_rate=1)
    assert engine.count("short pattern that does not fit") == 0
    assert engine.search("")  # empty pattern hits positions; at least the line
    assert engine.count(b"short") == 1


def test_save_and_load_round_trip(tmp_path: Path):
    engine = LogSieve.build("data/sample/synthetic_tiny.log", sample_rate=4)
    path = tmp_path / "index.pkl"
    engine.save(path)
    loaded = LogSieve.load(path)
    assert loaded.count("disk quota") == engine.count("disk quota")
    assert loaded.search("ada")[0].line_number == engine.search("ada")[0].line_number


def test_bad_pattern_type():
    engine = LogSieve.from_lines([b"abc"], sample_rate=1)
    with pytest.raises(TypeError):
        engine.count(12)  # type: ignore[arg-type]
