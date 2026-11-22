"""Baseline searchers: naive scan, KMP, str.find, and Aho-Corasick.

Knuth, Morris, and Pratt (1977) and Amakobe section 10.3 are the source of
the failure function. The code is a fresh port of the matcher I wrote for
CSC 5300 Week 11. Aho and Corasick (1975) build one automaton for a whole
watch list, which is the right comparison when an analyst has many patterns
and no index yet.

Every searcher uses the same hit rule as the FM-index. An empty pattern hits
every position. A pattern longer than the text hits nothing. Matches may
overlap. Return values are starting offsets, sorted ascending.
"""

from __future__ import annotations

from collections import deque


def naive_count(text: bytes, pattern: bytes) -> int:
    """Count hits without storing them. Same O(n m) scan as ``naive_search``."""

    _check_pair(text, pattern)
    n = len(text)
    if pattern == b"":
        return n
    m = len(pattern)
    if m > n:
        return 0
    count = 0
    start = 0
    first = pattern[:1]
    while start <= n - m:
        found = text.find(first, start, n - m + 1)
        if found < 0:
            break
        if text[found : found + m] == pattern:
            count += 1
        start = found + 1
    return count


def naive_search(text: bytes, pattern: bytes) -> list[int]:
    """Classic scan. Worst case O(n m) character comparisons.

    The first byte is skipped with ``bytes.find`` so logs, which are not the
    worst case, finish in reasonable time. A pattern of identical bytes still
    checks every alignment, so the worst case stays O(n m).
    """

    _check_pair(text, pattern)
    n = len(text)
    if pattern == b"":
        return list(range(n))
    m = len(pattern)
    if m > n:
        return []
    hits: list[int] = []
    start = 0
    first = pattern[:1]
    while start <= n - m:
        found = text.find(first, start, n - m + 1)
        if found < 0:
            break
        if text[found : found + m] == pattern:
            hits.append(found)
        start = found + 1
    return hits


def kmp_prefix(pattern: bytes) -> list[int]:
    """Longest proper prefix that is also a suffix, for each pattern position.

    Complexity is O(m).
    """

    if not isinstance(pattern, (bytes, bytearray)):
        raise TypeError("pattern must be bytes")
    m = len(pattern)
    pi = [0] * m
    length = 0
    i = 1
    while i < m:
        if pattern[i] == pattern[length]:
            length += 1
            pi[i] = length
            i += 1
        elif length > 0:
            length = pi[length - 1]
        else:
            pi[i] = 0
            i += 1
    return pi


def kmp_count(text: bytes, pattern: bytes) -> int:
    """Count hits with Knuth-Morris-Pratt. O(n + m), no hit list."""

    _check_pair(text, pattern)
    n = len(text)
    if pattern == b"":
        return n
    m = len(pattern)
    if m > n:
        return 0
    pi = kmp_prefix(pattern)
    count = 0
    matched = 0
    for symbol in text:
        while matched > 0 and pattern[matched] != symbol:
            matched = pi[matched - 1]
        if pattern[matched] == symbol:
            matched += 1
        if matched == m:
            count += 1
            matched = pi[matched - 1]
    return count


def kmp_search(text: bytes, pattern: bytes) -> list[int]:
    """Knuth-Morris-Pratt. O(n + m) time and O(m) extra memory."""

    _check_pair(text, pattern)
    n = len(text)
    if pattern == b"":
        return list(range(n))
    m = len(pattern)
    if m > n:
        return []
    pi = kmp_prefix(pattern)
    hits: list[int] = []
    matched = 0
    for i, symbol in enumerate(text):
        while matched > 0 and pattern[matched] != symbol:
            matched = pi[matched - 1]
        if pattern[matched] == symbol:
            matched += 1
        if matched == m:
            hits.append(i - m + 1)
            matched = pi[matched - 1]
    return hits


def find_count(text: bytes, pattern: bytes) -> int:
    """Count hits with ``bytes.find``. O(n m) worst case, no hit list."""

    _check_pair(text, pattern)
    n = len(text)
    if pattern == b"":
        return n
    m = len(pattern)
    if m > n:
        return 0
    count = 0
    start = 0
    while start <= n - m:
        found = text.find(pattern, start)
        if found < 0:
            break
        count += 1
        start = found + 1
    return count


def find_search(text: bytes, pattern: bytes) -> list[int]:
    """Repeated ``bytes.find``, allowing overlaps. The C loop is the fast scan.

    Complexity is O(n m) in the worst case and much less on typical logs.
    """

    _check_pair(text, pattern)
    n = len(text)
    if pattern == b"":
        return list(range(n))
    m = len(pattern)
    if m > n:
        return []
    hits: list[int] = []
    start = 0
    while start <= n - m:
        found = text.find(pattern, start)
        if found < 0:
            break
        hits.append(found)
        start = found + 1
    return hits


class _TrieNode:
    __slots__ = ("next", "fail", "out")

    def __init__(self) -> None:
        self.next: dict[int, _TrieNode] = {}
        self.fail: _TrieNode | None = None
        self.out: list[int] = []


class AhoCorasick:
    """Automaton for a fixed set of patterns.

    Build time is O(total pattern length). A scan of a text of length n
    reports every match in O(n + total pattern length + occ). Empty patterns
    are rejected because they would match at every position and hide the
    comparison this class is for.
    """

    def __init__(self, patterns: list[bytes]):
        if not patterns:
            raise ValueError("Aho-Corasick needs at least one pattern")
        self.patterns: list[bytes] = []
        for pattern in patterns:
            if not isinstance(pattern, (bytes, bytearray)):
                raise TypeError("patterns must be bytes")
            if len(pattern) == 0:
                raise ValueError("Aho-Corasick does not take an empty pattern")
            self.patterns.append(bytes(pattern))
        self.root = _TrieNode()
        for index, pattern in enumerate(self.patterns):
            node = self.root
            for symbol in pattern:
                node = node.next.setdefault(symbol, _TrieNode())
            node.out.append(index)
        queue: deque[_TrieNode] = deque()
        for child in self.root.next.values():
            child.fail = self.root
            queue.append(child)
        while queue:
            current = queue.popleft()
            for symbol, child in current.next.items():
                queue.append(child)
                fail = current.fail
                while fail is not None and symbol not in fail.next:
                    fail = fail.fail
                child.fail = fail.next[symbol] if fail is not None and symbol in fail.next else self.root
                child.out = child.out + child.fail.out

    def search(self, text: bytes) -> dict[bytes, list[int]]:
        """Map each pattern to the starting offsets where it occurs in ``text``."""

        if not isinstance(text, (bytes, bytearray)):
            raise TypeError("text must be bytes")
        found: dict[int, list[int]] = {i: [] for i in range(len(self.patterns))}
        node = self.root
        for index, symbol in enumerate(text):
            while node is not self.root and symbol not in node.next:
                assert node.fail is not None
                node = node.fail
            if symbol in node.next:
                node = node.next[symbol]
            for pattern_index in node.out:
                length = len(self.patterns[pattern_index])
                found[pattern_index].append(index - length + 1)
        return {self.patterns[i]: hits for i, hits in found.items()}


def _check_pair(text: bytes, pattern: bytes) -> None:
    if not isinstance(text, (bytes, bytearray)):
        raise TypeError("text must be bytes")
    if not isinstance(pattern, (bytes, bytearray)):
        raise TypeError("pattern must be bytes")
