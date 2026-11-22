"""LogSieve: a compressed full-text index for security log search.

The package builds a Ferragina-Manzini index (FM-index) over a log file.
The index is the Burrows-Wheeler Transform (BWT) of the text, stored in a
wavelet tree so rank queries are fast, plus a sampled suffix array for locate.
"""

__version__ = "0.1.0"

from logsieve.query import LogSieve, Match

__all__ = ["LogSieve", "Match", "__version__"]
