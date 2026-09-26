"""Tabulate a sweep log (sweep_free.sh output): per-N DAG CPU, per-session CPU, and doubling exponents.

Usage: python3 tabulate.py <sweep log> [session prefix to exclude, default X]
"""

import math
import re
import sys

WALL: re.Pattern[str] = re.compile(r"^WALL (\S+) ([\d.]+) s CPU ([\d.]+)\+([\d.]+)$")


def parse(lines: list[str]) -> dict[int, dict[str, float]]:
    def step(acc: tuple[int, dict[int, dict[str, float]]], line: str) -> tuple[int, dict[int, dict[str, float]]]:
        n, table = acc
        if line.startswith("== N"):
            return int(line[4:]), {**table, int(line[4:]): {}}
        m: re.Match[str] | None = WALL.match(line)
        return (n, {**table, n: {**table[n], m[1]: float(m[3]) + float(m[4])}}) if m else acc

    state: tuple[int, dict[int, dict[str, float]]] = (0, {})
    for line in lines:
        state = step(state, line.rstrip())
    return state[1]


def exponent(n0: int, t0: float, n1: int, t1: float) -> float:
    return math.log(t1 / t0) / math.log(n1 / n0)


def render(table: dict[int, dict[str, float]], exclude: str) -> str:
    ns: list[int] = sorted(table)
    sessions: list[str] = [s for s in table[ns[0]] if not s.startswith(exclude)]
    totals: dict[int, float] = {n: sum(table[n][s] for s in sessions) for n in ns}
    header: str = "| N | total CPU | exp | " + " | ".join(sessions) + " |"
    rule: str = "|" + "---|" * (3 + len(sessions))
    rows: list[str] = [
        f"| {n} | {totals[n]:.1f} | "
        + (f"{exponent(p, totals[p], n, totals[n]):.2f}" if p else "")
        + " | " + " | ".join(f"{table[n][s]:.1f}" for s in sessions) + " |"
        for p, n in zip([0] + ns[:-1], ns)
    ]
    return "\n".join([header, rule] + rows)


if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        print(render(parse(f.readlines()), sys.argv[2] if len(sys.argv) > 2 else "X"))
