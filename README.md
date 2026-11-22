# LogSieve

LogSieve is a compressed full text index for security log search. I built it for CSC 5300, Advanced Algorithms, with Dr. Moody Amakobe at Concordia University Texas. The repository root is the final project folder.

The index is a Ferragina-Manzini index (FM-index). It stores the Burrows-Wheeler Transform (BWT) of the log in a wavelet tree so a count query is a short backward search, and it keeps a sampled suffix array so a locate query can walk back to a text position. I compare that with a plain suffix array, with Knuth-Morris-Pratt (KMP), with Aho-Corasick for a watch list of many patterns, and with a naive scan. A Count-Min sketch is included as a streaming summary of which addresses show up most often. That sketch is a stretch goal and it is not on the search path.

The Week 14 launch is the proposal, this prototype, the tests, and a first benchmark. Week 15 is the full implementation and Week 16 is the writeup and the demo. The public repository is https://github.com/ovasquez-devenv/csc5300-capstone-compressed-log-search. The proposal is `docs/proposal.pdf` and the short technical report is `analysis/week14_report.md`. The license is MIT, so the instructor can clone the repository and run it.

## Install

You need Python 3.11 or newer. I will rerun this on Python 3.14. From the repository root:

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
```

The runtime dependencies are numpy, matplotlib, and pandas. pytest runs the tests. jupyter, nbformat, nbclient, and nbconvert run the notebook. Rebuilding the proposal PDF also needs the Python packages `markdown` and `weasyprint`, which are not required to run the index.

## Run the prototype

Build an index and then search it. The index is pickled under `.logsieve/`, which git ignores.

```bash
python -m logsieve.cli build data/sample/OpenSSH_2k.log
python -m logsieve.cli search "Failed password"
python -m logsieve.cli --verbose search "Invalid user"
```

`examples/quick_demo.py` builds the same sample and runs five queries: "Failed password", "Invalid user", "authentication failure", an address from that file, and "Accepted".

```bash
python examples/quick_demo.py
```

## Benchmarks

The harness times builds and count queries, records space, and writes charts. The default sizes are prefixes of 2,000, 10,000, and 50,000 lines. It repeats each timed call 5 times after one warmup, with the garbage collector turned off during the timed section. The seed is 5300. Every count is checked against the naive scan before a timing is kept.

```bash
python -m logsieve.cli bench
```

`--quick` is a small smoke test of the same code. The full run is meant to finish in a few minutes on a normal Windows PC. It uses `data/raw/SSH.log` when that file is present, and otherwise it uses the committed 2,000 line sample, so the larger prefixes only appear after you download the Loghub archive.

Outputs land in `results/`: `early_benchmarks.csv`, `early_benchmarks_summary.csv`, `space_measurements.csv`, `environment.json`, and the PNG charts. `environment.json` records the Python version, the operating system, the CPU, the RAM, the git commit, and the seed. If you rerun the benchmark on another machine, those files change and the tables in the proposal have to be refreshed from the new run. Every timing and size in the writeup comes from the CSV files this command writes.

## Notebook

`analysis/experiments.ipynb` is the experimental plan and the Week 14 runs. It calls the same harness, then prints the tables and the charts.

```bash
python -m jupyter nbconvert --to notebook --execute analysis/experiments.ipynb --inplace
```

## Tests

```bash
python -m pytest
```

The tests check the suffix array against a naive sort, the BWT round trip, wavelet rank and access, and every search method against the naive scan on random bytes and on slices of the sample logs.

## Data

Sample files and checksums are described in `data/README.md`. To fetch the Loghub archives into `data/raw/`:

```bash
python scripts/download_data.py
```

## Layout

`src/logsieve/` is the package. `docs/proposal.md` is the source of the proposal PDF. `docs/references.bib` is the bibliography. `docs/figures/architecture.dot` is the source of the architecture figure. `analysis/week14_report.md` is the five section technical report required with a code submission.
