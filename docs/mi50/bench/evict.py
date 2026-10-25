#!/usr/bin/env python3
"""Drop files from the page cache (posix_fadvise DONTNEED; no privileges needed) so engine A/B arms start equally cold.
   evict.py <file or dir>...   (dirs: every regular file below, symlinks followed once)"""
import os, sys
tot = 0
def ev(p):
    global tot
    try:
        fd = os.open(p, os.O_RDONLY)
    except OSError:
        return
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED); tot += os.fstat(fd).st_size
    finally:
        os.close(fd)
for a in sys.argv[1:]:
    if os.path.isdir(a):
        for r, _, fs in os.walk(a, followlinks=True):
            for f in fs: ev(os.path.join(r, f))
    else:
        ev(a)
print("evicted (advised) %.1f GB" % (tot / 1e9))
