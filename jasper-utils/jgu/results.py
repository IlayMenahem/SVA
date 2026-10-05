"""Parsers for jgu outputs (time.txt, JGU_* log lines, results.json) and CPU tallies."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

TIME_PREFIX = "JGU_TIME"
RESULT_PREFIX = "JGU_RESULT"
STATUS_PREFIX = "JGU_STATUS"
SAMPLE_PREFIX = "JGU_CPUSAMPLE"
RESULT_KINDS = frozenset({"assert", "cover"})


@dataclass(frozen=True)
class TimeRecord:
    """One GNU time record of a jg session (its reaped engine children included)."""

    wall_s: float
    user_s: float
    sys_s: float
    maxrss_kb: int

    @property
    def cpu_s(self) -> float:
        return self.user_s + self.sys_s


@dataclass(frozen=True)
class LogResult:
    """One `JGU_RESULT` line written by jglib's jgu::report."""

    tag: str
    id: str
    kind: str
    status: str
    engine: str
    time_s: str
    depth: str


@dataclass(frozen=True)
class RunRecord:
    """Everything jgu knows about one fetched run directory."""

    name: str
    exit_code: int | None
    time: TimeRecord | None
    sampled_cpu_s: float | None
    log_results: tuple[LogResult, ...]
    results: tuple[Mapping[str, object], ...] | None
    results_errors: tuple[str, ...]


@dataclass(frozen=True)
class CpuRow:
    """CPU totals of the runs in one group."""

    group: str
    runs: int
    untimed: int
    cpu_s: float
    wall_s: float
    sampled_cpu_s: float
    effective_cpu_s: float


def effective_cpu(time: TimeRecord | None, sampled_cpu_s: float | None) -> float | None:
    """The larger of GNU time's CPU (exact when jg exits by itself, far too low when it is
    killed) and the /proc sample (a lower bound that survives kills); None without either."""
    known = [value for value in (time.cpu_s if time else None, sampled_cpu_s) if value is not None]
    return max(known) if known else None


def parse_fields(line: str, prefix: str) -> dict[str, str] | None:
    """Fields of a `PREFIX key=value ...` line, or None if the line has another prefix."""
    parts = line.split()
    if not parts or parts[0] != prefix:
        return None
    return dict(part.split("=", 1) for part in parts[1:] if "=" in part)


def field_lines(text: str, prefix: str) -> list[dict[str, str]]:
    return [fields for line in text.splitlines() if (fields := parse_fields(line, prefix)) is not None]


def time_from_fields(fields: Mapping[str, str]) -> TimeRecord | None:
    try:
        return TimeRecord(
            wall_s=float(fields["wall"]),
            user_s=float(fields["user"]),
            sys_s=float(fields["sys"]),
            maxrss_kb=int(fields.get("maxrss_kb", "0")),
        )
    except (KeyError, ValueError):
        return None


def parse_time(text: str) -> TimeRecord | None:
    """The last JGU_TIME record in a time.txt (GNU time may add a status line before it)."""
    records = [record for fields in field_lines(text, TIME_PREFIX) if (record := time_from_fields(fields))]
    return records[-1] if records else None


def parse_sample(text: str) -> float | None:
    """total_cpu_s of the last JGU_CPUSAMPLE line written by cpu_sampler.py."""
    totals = [fields.get("total_cpu_s", "") for fields in field_lines(text, SAMPLE_PREFIX)]
    try:
        return float(totals[-1]) if totals else None
    except ValueError:
        return None


def parse_log_results(text: str) -> list[LogResult]:
    return [
        LogResult(
            tag=fields.get("tag", "-"),
            id=fields.get("id", "-"),
            kind=fields.get("kind", "-"),
            status=fields.get("status", "-"),
            engine=fields.get("engine", "-"),
            time_s=fields.get("time_s", "-"),
            depth=fields.get("depth", "-"),
        )
        for fields in field_lines(text, RESULT_PREFIX)
    ]


def property_errors(index: int, item: object) -> list[str]:
    """Schema errors of one results.json property (accelerate-sva-proofs references/recording.md)."""
    where = f"properties[{index}]"
    if not isinstance(item, dict):
        return [f"{where} must be an object"]
    errors = [
        f"{where}.{key} must be a nonempty string"
        for key in ("id", "status", "engine")
        if not (isinstance(item.get(key), str) and item[key].strip())
    ]
    if item.get("kind") not in RESULT_KINDS:
        errors.append(f"{where}.kind must be one of {sorted(RESULT_KINDS)}")
    assumed = item.get("assumed")
    if not (isinstance(assumed, list) and all(isinstance(a, str) and a for a in assumed)):
        errors.append(f"{where}.assumed must be a list of IDs")
    elif len(set(assumed)) != len(assumed):
        errors.append(f"{where}.assumed has duplicate IDs")
    time_s = item.get("time_s")
    if time_s is not None and not (type(time_s) in (int, float) and math.isfinite(time_s)):
        errors.append(f"{where}.time_s must be a finite number")
    return errors


def results_errors(data: object) -> list[str]:
    """Schema errors of a whole results.json document; empty when it is valid."""
    if not isinstance(data, dict) or not isinstance(data.get("properties"), list):
        return ["results must be an object with a properties list"]
    items: list[object] = data["properties"]
    ids = [item.get("id") for item in items if isinstance(item, dict)]
    duplicates = sorted(str(name) for name, count in Counter(ids).items() if count > 1)
    return [error for index, item in enumerate(items) for error in property_errors(index, item)] + [
        f"duplicate property id: {name}" for name in duplicates
    ]


def status_counts(statuses: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(statuses).items()))


def read_text(path: Path) -> str | None:
    return path.read_text(errors="replace") if path.is_file() else None


def parse_exit_code(text: str | None) -> int | None:
    try:
        return int(text.strip()) if text is not None else None
    except ValueError:
        return None


def load_results(path: Path) -> tuple[tuple[Mapping[str, object], ...] | None, tuple[str, ...]]:
    text = read_text(path)
    if text is None:
        return None, ()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        return None, (f"results.json is not JSON: {error}",)
    errors = tuple(results_errors(data))
    properties = data["properties"] if not errors else []
    return tuple(p for p in properties if isinstance(p, dict)), errors


def load_run(run_dir: Path) -> RunRecord:
    """Read the outputs that `jgu fetch` copied into run_dir."""
    results, errors = load_results(run_dir / "results.json")
    time_text = read_text(run_dir / "time.txt")
    sample_text = read_text(run_dir / "cpu_sample.txt")
    return RunRecord(
        name=run_dir.name,
        exit_code=parse_exit_code(read_text(run_dir / "exit_code")),
        time=parse_time(time_text) if time_text is not None else None,
        sampled_cpu_s=parse_sample(sample_text) if sample_text is not None else None,
        log_results=tuple(parse_log_results(read_text(run_dir / "jg.log") or "")),
        results=results,
        results_errors=errors,
    )


def group_of(name: str, pattern: re.Pattern[str] | None) -> str:
    """Group of a run name: the first capture group (or whole match) of pattern, else 'all'."""
    if pattern is None:
        return "all"
    match = pattern.search(name)
    if match is None:
        return "(unmatched)"
    return match.group(1) if pattern.groups else match.group(0)


def cpu_rows(
    runs: Sequence[tuple[str, TimeRecord | None, float | None]],
    pattern: re.Pattern[str] | None,
) -> list[CpuRow]:
    """Per-group CPU totals of (run name, time record, sampled cpu) triples, sorted by group."""
    groups = sorted({group_of(name, pattern) for name, _, _ in runs})

    def row(group: str) -> CpuRow:
        members = [(time, sampled) for name, time, sampled in runs if group_of(name, pattern) == group]
        timed = [time for time, _ in members if time is not None]
        effective = [effective_cpu(time, sampled) for time, sampled in members]
        return CpuRow(
            group=group,
            runs=len(members),
            untimed=len(members) - len(timed),
            cpu_s=sum(time.cpu_s for time in timed),
            wall_s=sum(time.wall_s for time in timed),
            sampled_cpu_s=sum(sampled for _, sampled in members if sampled is not None),
            effective_cpu_s=sum(value for value in effective if value is not None),
        )

    return [row(group) for group in groups]


def total_row(rows: Sequence[CpuRow]) -> CpuRow:
    return CpuRow(
        group="TOTAL",
        runs=sum(r.runs for r in rows),
        untimed=sum(r.untimed for r in rows),
        cpu_s=sum(r.cpu_s for r in rows),
        wall_s=sum(r.wall_s for r in rows),
        sampled_cpu_s=sum(r.sampled_cpu_s for r in rows),
        effective_cpu_s=sum(r.effective_cpu_s for r in rows),
    )


def format_cpu(rows: Sequence[CpuRow]) -> str:
    """Aligned table of the groups plus a total, then one JGU_CPU_TOTAL JSON line.
    effective_cpu_s is the number to report (see effective_cpu)."""
    total = total_row(rows)
    header = (
        f"{'group':<24} {'runs':>5} {'untimed':>7} {'time_cpu_s':>12} {'sampled_cpu_s':>14} "
        f"{'effective_cpu_s':>16} {'wall_s':>12}"
    )
    lines = [
        f"{r.group:<24} {r.runs:>5} {r.untimed:>7} {r.cpu_s:>12.1f} {r.sampled_cpu_s:>14.1f} "
        f"{r.effective_cpu_s:>16.1f} {r.wall_s:>12.1f}"
        for r in [*rows, total]
    ]
    summary = {
        "runs": total.runs,
        "untimed": total.untimed,
        "time_cpu_s": round(total.cpu_s, 2),
        "sampled_cpu_s": round(total.sampled_cpu_s, 2),
        "effective_cpu_s": round(total.effective_cpu_s, 2),
        "wall_s": round(total.wall_s, 2),
        "groups": {r.group: round(r.effective_cpu_s, 2) for r in rows},
    }
    return "\n".join([header, *lines, "JGU_CPU_TOTAL " + json.dumps(summary)])


def run_statuses(record: RunRecord) -> dict[str, int]:
    """Status counts from results.json, or from the JGU_RESULT log lines when it is absent."""
    if record.results is not None:
        return status_counts(str(p.get("status")) for p in record.results)
    return status_counts(r.status for r in record.log_results)


def results_state(record: RunRecord) -> str:
    if record.results_errors:
        return "invalid"
    return "missing" if record.results is None else "ok"


def seconds_field(name: str, value: float | None) -> str:
    return f"{name}={value:.1f}" if value is not None else f"{name}=-"


def format_run(record: RunRecord) -> str:
    """One JGU_SUMMARY line plus one line per results.json property and any schema errors."""
    time = record.time
    summary = " ".join(
        [
            "JGU_SUMMARY",
            f"run={record.name}",
            f"exit={record.exit_code if record.exit_code is not None else '-'}",
            seconds_field("wall_s", time.wall_s if time else None),
            seconds_field("time_cpu_s", time.cpu_s if time else None),
            seconds_field("sampled_cpu_s", record.sampled_cpu_s),
            seconds_field("effective_cpu_s", effective_cpu(time, record.sampled_cpu_s)),
            "results=" + (",".join(f"{k}:{v}" for k, v in run_statuses(record).items()) or "-"),
            f"results_json={results_state(record)}",
        ]
    )
    properties = [
        f"  {p.get('id')}: {p.get('kind')} {p.get('status')} engine={p.get('engine')} "
        f"assumed={','.join(map(str, p.get('assumed') or [])) or '-'}"
        for p in record.results or ()
    ]
    return "\n".join([summary, *properties, *(f"  error: {e}" for e in record.results_errors)])
