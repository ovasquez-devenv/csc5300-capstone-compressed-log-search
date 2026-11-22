"""FM-index count, locate, and extract against the naive scan."""

import random

import pytest

from logsieve.baselines import naive_search
from logsieve.fm_index import FMIndex
from logsieve.ingest import load_log


def _assert_same(text: bytes, pattern: bytes, sample_rate: int = 4) -> None:
    index = FMIndex(text, sample_rate=sample_rate)
    expect = naive_search(text, pattern)
    assert index.count(pattern) == len(expect)
    assert index.locate(pattern) == expect


def test_banana_count_and_locate():
    text = b"banana\x00"
    _assert_same(text, b"ana")
    _assert_same(text, b"a")
    _assert_same(text, b"banana")
    _assert_same(text, b"x")
    _assert_same(text, b"")
    _assert_same(text, b"bananazzz")


def test_edges_start_end_repeat_and_long_pattern():
    text = b"abcabc\x00"
    _assert_same(text, b"abc")
    _assert_same(text, b"bc\x00")
    _assert_same(text, b"\x00")
    text = b"aaaaaa\x00"
    _assert_same(text, b"aaa")
    _assert_same(text, b"a")
    _assert_same(b"q\x00", b"qqqq")


def test_extract_round_trip_and_slices():
    text = b"banana\x00"
    index = FMIndex(text, sample_rate=2)
    assert index.extract(0, len(text)) == text
    assert index.extract(1, 4) == b"ana"
    assert index.extract(0, 0) == b""
    assert index.extract(6, 7) == b"\x00"
    rng = random.Random(5300)
    body = bytes(rng.randrange(1, 8) for _ in range(80))
    text = body + b"\x00"
    index = FMIndex(text, sample_rate=3)
    assert index.extract(0, len(text)) == text
    for _ in range(20):
        start = rng.randrange(0, len(text))
        end = rng.randrange(start, len(text) + 1)
        assert index.extract(start, end) == text[start:end]


def test_sample_rates_agree():
    rng = random.Random(3)
    text = bytes(rng.randrange(1, 5) for _ in range(60)) + b"\x00"
    pattern = text[10:18]
    expect = naive_search(text, pattern)
    for rate in (1, 2, 4, 7, 16, 64):
        index = FMIndex(text, sample_rate=rate)
        assert index.locate(pattern) == expect
        assert index.count(pattern) == len(expect)


def test_random_strings_match_naive():
    rng = random.Random(5300)
    alphabet = b"abca\nXYZ"
    for n in (1, 8, 25, 70):
        body = bytes(alphabet[rng.randrange(len(alphabet))] for _ in range(n))
        text = body + b"\x00"
        index = FMIndex(text, sample_rate=5)
        patterns = [b"", b"a", b"\n", body[:1], body, b"nope", b"aaa"]
        if n >= 4:
            for _ in range(8):
                start = rng.randrange(n)
                length = rng.randint(1, min(6, n - start))
                patterns.append(body[start : start + length])
        for pattern in patterns:
            expect = naive_search(text, pattern)
            assert index.count(pattern) == len(expect)
            assert index.locate(pattern) == expect


def test_non_ascii_utf8_round_trip_search():
    text = "user café from 10.0.0.2\n".encode() + b"\x00"
    _assert_same(text, "café".encode())
    _assert_same(text, "10.0.0".encode())


def test_sample_log_substrings_match_naive():
    log = load_log("data/sample/OpenSSH_2k.log", max_lines=200)
    index = FMIndex(log.text, sample_rate=8)
    body = log.body
    rng = random.Random(5300)
    patterns = [
        b"Failed password",
        b"Invalid user",
        b"authentication failure",
        b"this pattern is absent zzqx",
        b"",
        body[:8],
        body[-12:],
    ]
    for _ in range(12):
        length = rng.choice([4, 8, 16])
        start = rng.randrange(0, len(body) - length)
        patterns.append(body[start : start + length])
    for pattern in patterns:
        expect = naive_search(log.text, pattern)
        assert index.count(pattern) == len(expect)
        assert index.locate(pattern) == expect


def test_bad_sample_rate_and_type():
    with pytest.raises(ValueError):
        FMIndex(b"a\x00", sample_rate=0)
    with pytest.raises(TypeError):
        FMIndex("abc")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        FMIndex(b"a\x00").count("a")  # type: ignore[arg-type]


def test_component_bytes_are_positive():
    index = FMIndex(b"banana\x00", sample_rate=2)
    parts = index.component_bytes()
    assert parts["fm_index_bytes"] > 0
    assert parts["wavelet_bits"] > 0
    assert parts["sample_count"] >= 1
