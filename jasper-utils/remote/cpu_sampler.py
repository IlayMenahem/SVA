#!/usr/bin/env python3
"""Sample the CPU time of every process in one session until a watched process exits.

Usage: cpu_sampler.py SESSION_ID WATCH_PID PERIOD_S OUT_FILE

GNU time only counts children that jg reaps; this sampler also sees engine workers
that are killed or never reaped. After every sample it rewrites OUT_FILE with one line

    JGU_CPUSAMPLE total_cpu_s=<s> procs=<n> peak_procs=<n> samples=<n>

so the latest value survives a kill. Processes that live shorter than one period are
missed, so the total is a lower bound. Runs on the hosts' Python 3.6: keep it 3.6-compatible.
"""

# Builtin generics and `X | None` annotations need Python 3.9/3.10; the hosts run 3.6.
# ruff: noqa: UP006, UP035, UP045
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

ProcessKey = Tuple[int, int]


def read_process(
    pid: int, ticks_per_s: float
) -> Optional[Tuple[int, ProcessKey, float]]:
    """Return (session id, (pid, start tick), cpu seconds) of one process, or None if it is gone."""
    try:
        with open(f"/proc/{pid}/stat") as stat:
            data = stat.read()
    except OSError:
        return None
    fields = data[data.rindex(")") + 2 :].split()
    session, utime, stime, start = (
        int(fields[3]),
        int(fields[11]),
        int(fields[12]),
        int(fields[19]),
    )
    return session, (pid, start), (utime + stime) / ticks_per_s


def session_cpu(session: int, ticks_per_s: float) -> Dict[ProcessKey, float]:
    """CPU seconds of each live process of a session, excluding this sampler."""
    own = os.getpid()
    pids = (
        int(name) for name in os.listdir("/proc") if name.isdigit() and int(name) != own
    )
    found = (read_process(pid, ticks_per_s) for pid in pids)
    return {key: cpu for sid, key, cpu in filter(None, found) if sid == session}


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def write_line(path: str, line: str) -> None:
    temporary = path + ".tmp"
    with open(temporary, "w") as out:
        out.write(line + "\n")
    os.replace(temporary, path)


def main(argv: List[str]) -> int:
    if len(argv) != 5:
        sys.stderr.write(__doc__)
        return 2
    session, watch_pid, period_s, out = (
        int(argv[1]),
        int(argv[2]),
        float(argv[3]),
        argv[4],
    )
    ticks_per_s = float(os.sysconf("SC_CLK_TCK"))
    latest = {}  # type: Dict[ProcessKey, float]
    peak, samples = 0, 0
    running = True
    while running:
        running = alive(watch_pid)
        current = session_cpu(session, ticks_per_s)
        latest.update(current)
        peak, samples = max(peak, len(current)), samples + 1
        write_line(
            out,
            f"JGU_CPUSAMPLE total_cpu_s={sum(latest.values()):.2f} procs={len(latest)} peak_procs={peak} samples={samples}",
        )
        if running:
            time.sleep(period_s)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
