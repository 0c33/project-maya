#!/usr/bin/env python3
"""NVMe read-latency probe: a 4 KiB O_DIRECT random read of <file> every 0.2 s; logs every read slower than 0.2 s
(and a heartbeat each minute) with a timestamp.  ioprobe.py <file> <log>"""
import os, sys, time, random, mmap
f, log = sys.argv[1], open(sys.argv[2], "a", buffering=1)
fd = os.open(f, os.O_RDONLY | os.O_DIRECT); size = os.fstat(fd).st_size
buf = mmap.mmap(-1, 4096); worst = 0.0; t_hb = time.time()
while True:
    off = random.randrange(0, size // 4096) * 4096
    t0 = time.time(); os.preadv(fd, [buf], off); dt = time.time() - t0
    worst = max(worst, dt)
    if dt > 0.2: log.write("%s SLOW read %.3f s at %d\n" % (time.strftime("%H:%M:%S"), dt, off))
    if time.time() - t_hb > 60: log.write("%s heartbeat worst %.4f s\n" % (time.strftime("%H:%M:%S"), worst)); worst = 0.0; t_hb = time.time()
    time.sleep(0.2)
