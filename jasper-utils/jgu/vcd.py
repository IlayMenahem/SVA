"""Read VCD traces (e.g. from jglib's jgu::save_vcd) as per-cycle tables."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

DEFAULT_CLOCK = r"(^|\.)(clk|clock|clk_i)$"
KEYWORDS_WITHOUT_VALUES = frozenset({"$dumpvars", "$dumpall", "$dumpon", "$dumpoff", "$end"})


@dataclass(frozen=True)
class Signal:
    code: str
    name: str
    width: int


@dataclass(frozen=True)
class Vcd:
    """Declared signals and the value changes, in file order."""

    signals: tuple[Signal, ...]
    changes: tuple[tuple[int, str, str], ...]


def split_header(text: str) -> tuple[list[str], list[str]]:
    """Header tokens up to and including `$enddefinitions $end`, and the body tokens."""
    tokens = text.split()
    for index in range(len(tokens) - 1):
        if tokens[index] == "$enddefinitions" and tokens[index + 1] == "$end":
            return tokens[: index + 2], tokens[index + 2 :]
    raise ValueError("not a VCD file: no $enddefinitions")


def header_signals(tokens: Sequence[str]) -> list[Signal]:
    """Signals of the `$var` declarations, named by their full scope path."""
    scopes: list[str] = []
    signals: list[Signal] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "$scope":
            scopes.append(tokens[index + 2])
        elif token == "$upscope":
            scopes.pop()
        elif token == "$var":
            width, code, reference = int(tokens[index + 2]), tokens[index + 3], tokens[index + 4]
            signals.append(Signal(code=code, name=".".join([*scopes, reference]), width=width))
        index += 1
    return signals


def body_changes(tokens: Sequence[str]) -> list[tuple[int, str, str]]:
    """(time, id code, value) of every value change; vector values keep their bit string."""
    changes: list[tuple[int, str, str]] = []
    now = 0
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("#"):
            now = int(token[1:])
        elif token[0] in "bBrR":
            changes.append((now, tokens[index + 1], token[1:].lower()))
            index += 1
        elif token not in KEYWORDS_WITHOUT_VALUES and token[0] in "01xXzZ":
            changes.append((now, token[1:], token[0].lower()))
        index += 1
    return changes


def parse_vcd(text: str) -> Vcd:
    header, body = split_header(text)
    return Vcd(signals=tuple(header_signals(header)), changes=tuple(body_changes(body)))


def find_signals(vcd: Vcd, patterns: Iterable[str]) -> list[Signal]:
    """Signals whose full name matches any regex, in declaration order, without duplicates."""
    compiled = [re.compile(p) for p in patterns]
    first_by_name: dict[str, Signal] = {}
    for signal in vcd.signals:
        if any(c.search(signal.name) for c in compiled):
            first_by_name.setdefault(signal.name, signal)
    return list(first_by_name.values())


def rising_edges(vcd: Vcd, clock: Signal) -> list[int]:
    """Times at which the clock changes to 1 from any other value."""
    edges: list[int] = []
    previous = "x"
    for now, code, value in vcd.changes:
        if code == clock.code:
            if value == "1" and previous != "1":
                edges.append(now)
            previous = value
    return edges


def values_before(vcd: Vcd, codes: set[str], times: Sequence[int]) -> list[dict[str, str]]:
    """For each sample time, the value of each code just before that time (x if never set)."""
    state = {code: "x" for code in codes}
    samples: list[dict[str, str]] = []
    changes = iter(vcd.changes)
    pending = next(changes, None)
    for sample_time in times:
        while pending is not None and pending[0] < sample_time:
            if pending[1] in state:
                state[pending[1]] = pending[2]
            pending = next(changes, None)
        samples.append(dict(state))
    return samples


def cycle_values(vcd: Vcd, signals: Sequence[Signal], clock: Signal) -> list[dict[str, str]]:
    """Row k: values held between rising edge k and rising edge k+1 (the last row: final values)."""
    edges = rising_edges(vcd, clock)
    end = max((now for now, _, _ in vcd.changes), default=0) + 1
    return values_before(vcd, {s.code for s in signals}, [*edges[1:], end] if edges else [])


def format_value(bits: str, width: int, radix: str) -> str:
    """Render a VCD bit string; values with x/z bits stay binary."""
    if width == 1 or radix == "bin" or any(b not in "01" for b in bits):
        return bits
    number = int(bits, 2)
    return str(number) if radix == "dec" else f"0x{number:0{(width + 3) // 4}x}"


def table(vcd: Vcd, signals: Sequence[Signal], clock: Signal, radix: str = "hex", first_cycle: int = 1) -> str:
    """Tab-separated table: one row per clock cycle, one column per signal. Cycles are numbered
    from first_cycle; the default 1 matches Jasper's trace numbering."""
    rows = cycle_values(vcd, signals, clock)
    header = "\t".join(["cycle", *(s.name for s in signals)])
    body = [
        "\t".join([str(cycle), *(format_value(row[s.code], s.width, radix) for s in signals)])
        for cycle, row in enumerate(rows, start=first_cycle)
    ]
    return "\n".join([header, *body])


def single_signal(vcd: Vcd, pattern: str, role: str) -> Signal:
    matches = find_signals(vcd, [pattern])
    if len(matches) != 1:
        names = ", ".join(s.name for s in matches[:5]) or "none"
        raise ValueError(f"{role} pattern {pattern!r} must match one signal; matched {names}")
    return matches[0]
