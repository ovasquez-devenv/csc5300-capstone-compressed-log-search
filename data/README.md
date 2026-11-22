# Data

The logs in this project come from Loghub (Zhu et al. 2023). The project page is https://github.com/logpai/loghub and the archive I used is Zenodo record 8196385. Loghub says the datasets are free to use for research or academic work, and it asks people who use them to cite the Loghub paper and to point back at the repository. I am not redistributing the big archives. Those stay in `data/raw/`, which git ignores. The two small samples are committed so the tests and the demo run without a download.

`data/sample/OpenSSH_2k.log` is the OpenSSH 2,000 line sample from the logpai/loghub repository. The file is 225,216 bytes. It contains 1,999 newline bytes and the last line has no trailing newline, so a line reader returns 2,000 lines. SHA 256: `1e4912727fa88245113d41b16a0cd25ceadba7f931e1c406542885b91254264f`.

`data/sample/Linux_2k.log` is the Linux 2,000 line sample from the same repository. The file is 216,485 bytes, with the same newline quirk, so it is also 2,000 lines. SHA 256: `b3e20bc1afe732ab1bf3ed1de4bf9c809e4194e02f7dea911d918e5342e8e173`.

`data/sample/synthetic_tiny.log` is a six line file I wrote for the unit tests. It is not a Loghub file. SHA 256: `f6fb5150cccbca1b0906995d8569ea6b00c7d984d826a617e99174fab1930a55`.

The larger files, fetched by `python scripts/download_data.py`, are the Zenodo archives. I checked the MD5 values against the Zenodo record API and I also recorded SHA 256 of the copies I downloaded.

OpenSSH is `SSH.tar.gz`, 4,596,666 bytes, MD5 `a44e40b4348697dabf2bba56885e0a38`, SHA 256 `296610a35773f58b7c295e5407fc5ccdf48beb3c544fc14a6309addf904a2712`. Unpacked, `SSH.log` is 73,417,506 bytes. It contains 655,146 newline bytes and does not end with a newline, so a line reader returns 655,147 lines. Loghub's table lists 655,146 lines and 70.02 MiB, which matches the newline count and the byte size (73,417,506 bytes is about 70.02 MiB).

Linux is `Linux.tar.gz`, 232,039 bytes, MD5 `6d1802d7778126f21c001c6aa7b6b106`, SHA 256 `7e1f820d8d45ae086032e515d9ce8d079a102a9b37dcff5b41a8e60b1f857820`. Unpacked, `Linux.log` is 2,349,686 bytes and 25,567 lines. That matches the Loghub table (2.25 MiB, 25,567 lines).

Apache is `Apache.tar.gz`, 262,905 bytes, MD5 `de9a42d12f9b60612631c67a5a9f8628`, SHA 256 `f2cb5014453c8a0f71596838e1639a2131ff6d360839ad280409f621a6cac452`. Unpacked, `Apache.log` is 5,135,876 bytes. It has 56,481 newline bytes and no trailing newline on the last line, so a line reader returns 56,482 lines. Loghub's table lists 56,481 lines and 4.90 MiB.

Week 14 benchmarks read prefixes of `SSH.log` (2,000, 10,000, and 50,000 lines) plus the committed Linux sample. The 1 MB to 20 MB prefixes are left for Week 15, after the build is faster. If `data/raw/SSH.log` is missing, the harness falls back to the committed OpenSSH sample and the larger prefixes shrink to whatever that file contains.
