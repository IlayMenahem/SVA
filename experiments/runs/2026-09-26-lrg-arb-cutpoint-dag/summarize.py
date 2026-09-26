"""Summarize sweep output: per N, sessions, wall (from launch to last exit), summed CPU, result counts.

Usage: python3 summarize.py <sweep output file>
"""

import collections
import re
import sys

WALL_RE: re.Pattern[str] = re.compile(r"^WALL (\S+) ([\d.]+) s CPU ([\d.]+)\+([\d.]+)")
COUNT_RE: re.Pattern[str] = re.compile(r"^\s+(\S+)\s+(\d+) (\w+)$")


def section_rows(text: str) -> list[tuple[str, str]]:
    sections: list[str] = re.split(r"^== ", text, flags=re.M)[1:]
    return [(s.split("\n", 1)[0].strip(), s) for s in sections if "TOTAL_WALL" in s]


def summarize(name: str, body: str) -> str:
    walls: list[tuple[str, float, float]] = [
        (m[1], float(m[2]), float(m[3]) + float(m[4]))
        for m in map(WALL_RE.match, body.splitlines()) if m]
    dag: list[tuple[str, float, float]] = [w for w in walls if not w[0].startswith("X")]
    counts: collections.Counter[str] = collections.Counter()
    for m in filter(None, map(COUNT_RE.match, body.splitlines())):
        counts[f"{'X' if m[1].startswith('X') else 'dag'}:{m[3]}"] += int(m[2])
    total: re.Match[str] | None = re.search(r"TOTAL_WALL ([\d.]+)", body)
    slowest: tuple[str, float, float] = max(dag, key=lambda w: w[1])
    return (f"{name}: sessions={len(dag)} total_wall={float(total[1]) if total else float('nan'):.1f}s "
            f"cpu={sum(w[2] for w in dag):.1f}s slowest={slowest[0]}:{slowest[1]:.1f}s "
            f"{dict(sorted(counts.items()))}")


def main(argv: list[str]) -> None:
    text: str = open(argv[1]).read()
    print("\n".join(summarize(name, body) for name, body in section_rows(text)))


if __name__ == "__main__":
    main(sys.argv)
