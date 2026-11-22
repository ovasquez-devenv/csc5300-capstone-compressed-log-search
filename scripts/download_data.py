"""Download Loghub files and check them against known checksums.

The 2,000 line samples land in data/sample. The larger archives land in
data/raw, which is gitignored. Checksums below were computed from the copies
used in this project, and the archive MD5 values match the Zenodo record
8196385 API.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SAMPLES = {
    "OpenSSH_2k.log": {
        "url": "https://raw.githubusercontent.com/logpai/loghub/master/OpenSSH/OpenSSH_2k.log",
        "sha256": "1e4912727fa88245113d41b16a0cd25ceadba7f931e1c406542885b91254264f",
        "dest": ROOT / "data" / "sample" / "OpenSSH_2k.log",
    },
    "Linux_2k.log": {
        "url": "https://raw.githubusercontent.com/logpai/loghub/master/Linux/Linux_2k.log",
        "sha256": "b3e20bc1afe732ab1bf3ed1de4bf9c809e4194e02f7dea911d918e5342e8e173",
        "dest": ROOT / "data" / "sample" / "Linux_2k.log",
    },
}

ARCHIVES = {
    "SSH.tar.gz": {
        "url": "https://zenodo.org/api/records/8196385/files/SSH.tar.gz/content",
        "md5": "a44e40b4348697dabf2bba56885e0a38",
        "sha256": "296610a35773f58b7c295e5407fc5ccdf48beb3c544fc14a6309addf904a2712",
    },
    "Linux.tar.gz": {
        "url": "https://zenodo.org/api/records/8196385/files/Linux.tar.gz/content",
        "md5": "6d1802d7778126f21c001c6aa7b6b106",
        "sha256": "7e1f820d8d45ae086032e515d9ce8d079a102a9b37dcff5b41a8e60b1f857820",
    },
    "Apache.tar.gz": {
        "url": "https://zenodo.org/api/records/8196385/files/Apache.tar.gz/content",
        "md5": "de9a42d12f9b60612631c67a5a9f8628",
        "sha256": "f2cb5014453c8a0f71596838e1639a2131ff6d360839ad280409f621a6cac452",
    },
}


def _digest(path: Path, algo: str) -> str:
    hasher = hashlib.new(algo)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _fetch(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print("downloading %s" % url)
    urllib.request.urlretrieve(url, dest)


def _need(path: Path, algo: str, expected: str) -> bool:
    if not path.exists():
        return True
    got = _digest(path, algo)
    if got != expected:
        print("checksum mismatch for %s, downloading again" % path)
        return True
    print("ok %s" % path)
    return False


def main() -> int:
    for spec in SAMPLES.values():
        dest = spec["dest"]
        if _need(dest, "sha256", spec["sha256"]):
            _fetch(spec["url"], dest)
            got = _digest(dest, "sha256")
            if got != spec["sha256"]:
                print("sha256 mismatch for %s: %s" % (dest, got), file=sys.stderr)
                return 1
    raw = ROOT / "data" / "raw"
    for name, spec in ARCHIVES.items():
        dest = raw / name
        if _need(dest, "md5", spec["md5"]):
            _fetch(spec["url"], dest)
        got_md5 = _digest(dest, "md5")
        got_sha = _digest(dest, "sha256")
        if got_md5 != spec["md5"] or got_sha != spec["sha256"]:
            print("checksum mismatch for %s" % name, file=sys.stderr)
            print("md5 %s" % got_md5, file=sys.stderr)
            print("sha256 %s" % got_sha, file=sys.stderr)
            return 1
        print("ok %s" % dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
