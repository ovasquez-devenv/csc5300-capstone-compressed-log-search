"""Naive scan, KMP, str.find, and Aho-Corasick agree with each other."""

import random

import pytest

from logsieve.baselines import (
    AhoCorasick,
    find_search,
    kmp_prefix,
    kmp_search,
    naive_search,
)
from logsieve.fm_index import FMIndex
from logsieve.ingest import load_log
from logsieve.suffix_array import build_suffix_array, suffix_array_search


def test_kmp_prefix_known_value():
    # pattern: a b a b a c
    assert kmp_prefix(b"ababaca") == [0, 0, 1, 2, 3, 0, 1]


def test_all_single_pattern_methods_agree_on_random_text():
    rng = random.Random(5300)
    alphabet = b"abc01 \n"
    for n in (0, 1, 5, 40, 120):
        text = bytes(alphabet[rng.randrange(len(alphabet))] for _ in range(n))
        patterns = [b"", b"a", b"abc", b"aaa", b"zzzz", text[:1] if text else b"a"]
        if n >= 3:
            for _ in range(10):
                start = rng.randrange(n)
                length = rng.randint(1, min(8, n - start))
                patterns.append(text[start : start + length])
        for pattern in patterns:
            expect = naive_search(text, pattern)
            assert kmp_search(text, pattern) == expect
            assert find_search(text, pattern) == expect
            if n <= 80:
                sa = build_suffix_array(text)
                assert suffix_array_search(text, sa, pattern) == expect
                assert FMIndex(text + b"\x00", sample_rate=3).locate(pattern) == naive_search(
                    text + b"\x00", pattern
                )


def test_overlapping_and_edges():
    text = b"aaaa"
    expect = [0, 1, 2]
    assert naive_search(text, b"aa") == expect
    assert kmp_search(text, b"aa") == expect
    assert find_search(text, b"aa") == expect
    assert naive_search(b"abcdef", b"abc") == [0]
    assert naive_search(b"abcdef", b"def") == [3]
    assert naive_search(b"abcdef", b"xyzxyzxyz") == []
    assert kmp_search(b"abcdef", b"") == list(range(6))


def test_aho_corasick_matches_naive_including_overlaps_and_prefixes():
    text = b"she sells seashells"
    patterns = [b"she", b"he", b"sea", b"shell", b"sells", b"s"]
    auto = AhoCorasick(patterns)
    found = auto.search(text)
    for pattern in patterns:
        assert found[pattern] == naive_search(text, pattern)
    text = b"aaaa"
    auto = AhoCorasick([b"a", b"aa", b"aaa"])
    found = auto.search(text)
    assert found[b"a"] == [0, 1, 2, 3]
    assert found[b"aa"] == [0, 1, 2]
    assert found[b"aaa"] == [0, 1]


def test_aho_on_random_watch_list_and_sample_log():
    rng = random.Random(5300)
    text = bytes(rng.randrange(4) for _ in range(200))
    patterns = []
    for _ in range(15):
        start = rng.randrange(len(text) - 3)
        patterns.append(text[start : start + rng.choice([2, 3, 4])])
    patterns.append(b"zzzz-absent")
    found = AhoCorasick(patterns).search(text)
    for pattern in set(patterns):
        assert found[pattern] == naive_search(text, pattern)

    log = load_log("data/sample/Linux_2k.log", max_lines=150)
    watch = [b"failure", b"error", b"combo", b"no-such-token"]
    body = log.body
    for _ in range(8):
        start = rng.randrange(0, len(body) - 6)
        watch.append(body[start : start + 6])
    found = AhoCorasick(watch).search(log.text)
    for pattern in set(watch):
        assert found[pattern] == naive_search(log.text, pattern)


def test_aho_rejects_empty_pattern():
    with pytest.raises(ValueError):
        AhoCorasick([b"a", b""])
    with pytest.raises(ValueError):
        AhoCorasick([])


def test_type_errors():
    with pytest.raises(TypeError):
        naive_search("abc", b"a")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        kmp_search(b"abc", "a")  # type: ignore[arg-type]
