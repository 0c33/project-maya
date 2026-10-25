#!/usr/bin/env python3
"""When maya's decode progress stops for >8 s (serve log: same token count), dump each maya-ds4 thread's state + kernel
wait channel and /proc/pressure.  stallcatch.py <serve log> <out log>"""
import os, re, sys, time, collections
logf, out = sys.argv[1], open(sys.argv[2], "a", buffering=1)
def pid():
    for p in os.listdir("/proc"):
        if p.isdigit():
            try:
                if open("/proc/%s/comm" % p).read().strip().startswith("maya-ds4"): return p
            except OSError: pass
def dump(tag):
    p = pid(); out.write("=== %s %s pid %s\n" % (time.strftime("%H:%M:%S"), tag, p))
    if not p: return
    c = collections.Counter()
    for t in os.listdir("/proc/%s/task" % p):
        try:
            st = open("/proc/%s/task/%s/stat" % (p, t)).read().split(")")[1].split()[0]
            wc = open("/proc/%s/task/%s/wchan" % (p, t)).read().strip() or "-"
            c[(st, wc)] += 1
        except OSError: pass
    for (st, wc), n in c.most_common(): out.write("  %3d threads  state %s  wchan %s\n" % (n, st, wc))
    for r in ("io", "memory", "cpu"):
        out.write("  psi %s: %s\n" % (r, open("/proc/pressure/" + r).read().replace("\n", " | ")))
last = (None, time.time()); dumped = 0
while True:
    try: tail = open(logf).read()[-4000:]
    except OSError: tail = ""
    m = re.findall(r"(?:thinking|answering|writing a tool call[^:]*): (\d+) of max", tail)
    done_after = tail.rfind("done:") > tail.rfind("of max")
    cur = m[-1] if m and not done_after else None
    if cur != last[0]: last = (cur, time.time()); dumped = 0
    elif cur is not None and time.time() - last[1] > 8 and dumped < 3: dump("stall at token %s" % cur); dumped += 1; time.sleep(4)
    time.sleep(1)
