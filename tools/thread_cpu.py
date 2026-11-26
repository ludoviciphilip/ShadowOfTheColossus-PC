#!/usr/bin/env python3
"""Per-thread CPU use of the running bb-probe over a window, from /proc (no perf needed):
thread_cpu.py [seconds] -> name, tid, % of one core, the CPU it last ran on."""
import os, sys, time, subprocess

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 10
pid = subprocess.run(['pgrep', '-f', 'out/bb-probe out/boot-linked'], capture_output=True, text=True).stdout.split()
if not pid:
    sys.exit('bb-probe not running')
pid = pid[0]
tick = os.sysconf('SC_CLK_TCK')


def snap():
    rows = {}
    for tid in os.listdir(f'/proc/{pid}/task'):
        try:
            name = open(f'/proc/{pid}/task/{tid}/comm').read().strip()
            stat = open(f'/proc/{pid}/task/{tid}/stat').read()
            f = stat[stat.rfind(')') + 2:].split()
            rows[tid] = (name, int(f[11]) + int(f[12]), int(f[36]))  # utime+stime, processor
        except OSError:
            pass
    return rows


a = snap(); t0 = time.time(); time.sleep(secs); b = snap(); dt = time.time() - t0
out = []
for tid, (name, ticks, cpu) in b.items():
    if tid in a:
        out.append((100.0 * (ticks - a[tid][1]) / tick / dt, name, tid, cpu))
out.sort(reverse=True)
total = sum(r[0] for r in out)
print(f'{len(out)} threads, total {total:.0f}% of one core over {dt:.1f} s')
for pct, name, tid, cpu in out[:25]:
    print(f'{pct:6.1f}%  {name:16s} tid {tid:>8s}  cpu {cpu}')
