"""Count-Min sketch: no underestimates, and a basic IP count."""

from collections import Counter

import pytest

from logsieve.ingest import load_log
from logsieve.sketch import CountMinSketch, exact_ip_counts, ipv4_addresses


def test_never_underestimates_and_exact_on_a_tiny_stream():
    sketch = CountMinSketch(width=64, depth=4, seed=5300)
    items = [b"a", b"b", b"a", b"a", b"c"]
    for item in items:
        sketch.update(item)
    exact = Counter(items)
    for item, count in exact.items():
        assert sketch.query(item) >= count
    # With a wide table and a short stream the estimate is often exact.
    assert sketch.query(b"a") == 3
    assert sketch.query(b"missing") >= 0


def test_error_shrinks_as_the_table_grows():
    stream = [b"ip-%d" % (i % 20) for i in range(400)]
    exact = Counter(stream)
    wide = CountMinSketch.from_error(0.01, 0.01, seed=5300)
    narrow = CountMinSketch(width=4, depth=2, seed=5300)
    for item in stream:
        wide.update(item)
        narrow.update(item)
    wide_error = max(wide.query(item) - exact[item] for item in exact)
    narrow_error = max(narrow.query(item) - exact[item] for item in exact)
    assert wide_error <= narrow_error
    assert wide.nbytes() > narrow.nbytes()


def test_negative_update_rejected():
    sketch = CountMinSketch(8, 2, seed=1)
    with pytest.raises(ValueError):
        sketch.update(b"a", -1)


def test_ipv4_tokens_and_openssh_counts():
    assert ipv4_addresses(b"from 173.234.31.186 port 22") == [b"173.234.31.186"]
    assert ipv4_addresses(b"no address here") == []
    assert ipv4_addresses(b"10.0.0.8 and 10.1.2.3") == [b"10.0.0.8", b"10.1.2.3"]
    log = load_log("data/sample/OpenSSH_2k.log", max_lines=400)
    exact = exact_ip_counts(log.lines)
    assert exact
    narrow = CountMinSketch(width=8, depth=2, seed=5300)
    wide = CountMinSketch(width=400, depth=5, seed=5300)
    for line in log.lines:
        for address in ipv4_addresses(line):
            narrow.update(address)
            wide.update(address)
    narrow_error = 0
    wide_error = 0
    for address, count in exact.items():
        narrow_est = narrow.query(address)
        wide_est = wide.query(address)
        assert narrow_est >= count
        assert wide_est >= count
        narrow_error = max(narrow_error, narrow_est - count)
        wide_error = max(wide_error, wide_est - count)
    assert wide_error <= narrow_error


def test_from_error_parameter_checks():
    with pytest.raises(ValueError):
        CountMinSketch.from_error(0, 0.1)
    with pytest.raises(ValueError):
        CountMinSketch(width=1, depth=1)
