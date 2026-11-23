# LogSieve Week 14 technical report

Omar Vasquez, CSC 5300 Advanced Algorithms, Dr. Moody Amakobe. The repository root is the final project folder.

## Executive Summary

LogSieve is a Ferragina-Manzini index (FM-index) for exact substring search over security logs. The index is the Burrows-Wheeler Transform (BWT) of the log, stored in a wavelet tree, plus a sampled suffix array that maps a hit back to a line. I compared count time with a plain suffix array, Knuth-Morris-Pratt (KMP), a `str.find` loop, and a naive scan, on prefixes of the Loghub OpenSSH log. On the 50,000 line prefix the index builds in a median of 7.855 seconds. A count, at the median across the workload, is faster than the scans and slower than binary search on the suffix array. The measured index is 16,296,974 bytes, against 22,244,152 bytes for an int32 suffix array and 200,197,424 bytes for the same array as a Python list. A single watch list pass still belongs to Aho-Corasick. These figures are five trials on my Windows 11 PC with Python 3.14.7.

## Methodology

The text is the OpenSSH log from Loghub (Zhu et al. 2023), unpacked from Zenodo record 8196385. The harness read the first 2,000, 10,000, and 50,000 lines, which are 223,218, 1,098,049, and 5,561,038 bytes. Every count was checked against the naive scan before it was timed. Each timed call was repeated five times after one warmup, with the garbage collector disabled during the call. I report the mean, the sample standard deviation, the median, and the interquartile range. The seed is 5300. The machine in `results/environment.json`, commit `b256467a0834afc261c2eda2dabeece74c9efb43`, is my PC ODIS_LLC: CPython 3.14.7, Windows-11-10.0.26200-SP0, processor string "AMD64 Family 26 Model 104 Stepping 0, AuthenticAMD", 12 logical CPUs, numpy 2.5.5. The file marks the tree dirty and records no RAM total. Locate and the watch list used the 2,000 line prefix.

## Results

The build is mostly the suffix array. On 50,000 lines the median total is 7.855 seconds (mean 7.948 seconds, standard deviation 0.205 seconds, interquartile range 0.329 seconds). The suffix array phase median is 7.106 seconds, the wavelet median is 0.251 seconds, and the BWT median is 0.0339 seconds. The log log slope of median build time against text bytes, across the three sizes, is 1.179.

At 50,000 lines the median of the per pattern median count times is 0.0092 milliseconds for suffix array binary search, 0.103 milliseconds for the FM-index, 1.957 milliseconds for `str.find`, 30.44 milliseconds for the naive scan, and 236.6 milliseconds for KMP. Against `str.find`, the index is slower per query at 2,000 lines, so there is no break even. It pays for the build after 3,741 count queries at 10,000 lines and after 4,237 count queries at 50,000 lines.

Locate of the pattern "error" (47 hits) on the 2,000 line prefix moves from a median of 2.38 milliseconds at sample rate 4, with 892,896 bytes of samples, to 14.4 milliseconds at sample rate 64, with 55,824 bytes of samples. On a watch list of 100 patterns, Aho-Corasick takes a median of 0.0335 seconds and repeated FM-index counts take 0.00731 seconds, but the 2,000 line build is 0.178 seconds, so one batch is cheaper online. The Count-Min sketch saw 124 addresses and 47,320 updates. The exact counter is 13,912 bytes. A width 64 sketch is 2,048 bytes and overestimates by as much as 4,827. A width 1,024 sketch is 32,768 bytes and still overestimates by as much as 379.

## Discussion

The median across patterns keeps one order: suffix array, then the FM-index, then `str.find`, then the naive scan, then KMP. That is not the order of every pattern. On the long slice that starts "hd[24486]", `str.find` (0.536 milliseconds) beats the FM-index count (0.700 milliseconds). On "Invalid user" the naive scan beats `str.find`. The wavelet holds 6.61 bits per character on the large OpenSSH prefix and 6.02 bits per character on a random control of the same length. The tree follows byte values, and it does not Huffman compress the repeats. The index is still smaller than the int32 suffix array, and it is much smaller than a Python list of suffix positions. The sample rate still trades speed for memory on the small prefix. A one shot watch list belongs to Aho-Corasick. Dividing the 0.178 second build by the gap between the 100 pattern query medians gives about 6.8 batches before the index is ahead.

KMP's time is partly the interpreter. The naive scan and `str.find` skip in C, while KMP walks every byte in Python. I treat that gap as an implementation effect. With only 124 addresses, the exact counter is the better summary. The sketch is for a key set that does not fit, and this one does.

## Conclusion

The prototype builds, counts, locates, and agrees with the naive scan. On this Windows PC the FM-index is a reasonable count structure once a few thousand queries can pay for the build, suffix array binary search is still the faster count, and the space advantage is large against Python objects and modest against an int32 array. The median order is not every pattern's order. Week 15 must speed up the suffix array build and repeat locate and the watch list on longer prefixes. Week 16 writes those results against the threats already named: one PC, an interpreter mixed with C, and prefixes that stop at 5,561,038 bytes until the build is cheaper.
