"""Run EBMC under a wall-clock limit and classify its per-property results."""

import re
import resource
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from lrg_arb_rtl import REPO

EBMC: Final[Path] = REPO / "experiments/ebmc/hw-cbmc/src/ebmc/ebmc"
INDUCTION_1: Final[tuple[str, ...]] = ("--k-induction", "--bound", "1")
RESULT_LINE: Final[re.Pattern[str]] = re.compile(
    r"^\[(?P<id>[^\]]+)\] .*: (?P<status>[A-Z][A-Za-z0-9 ]*)$", re.MULTILINE
)


@dataclass(frozen=True)
class EbmcRun:
    command: tuple[str, ...]
    exit_code: int | None
    wall_s: float
    cpu_s: float
    results: dict[str, str]

    @property
    def verdict(self) -> str:
        """proved | refuted | inconclusive | bounded | timeout | error, over asserts only."""
        statuses = [status for key, status in self.results.items() if ".assert." in key]
        if self.exit_code is None:
            return "timeout"
        if not statuses:
            return "error"
        if "REFUTED" in statuses:
            return "refuted"
        if all(status == "PROVED" for status in statuses):
            return "proved"
        if all(status.startswith("PROVED up to bound") for status in statuses):
            return "bounded"
        return "inconclusive"


def ebmc_command(sv: Path, uses_reset: bool, engine: tuple[str, ...]) -> tuple[str, ...]:
    reset = ("--reset", "main.rst") if uses_reset else ()
    return (str(EBMC), str(sv), "--top", "main", *reset, *engine)


def children_cpu_s() -> float:
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return usage.ru_utime + usage.ru_stime


def decode(output: bytes | str | None) -> str:
    if isinstance(output, bytes):
        return output.decode(errors="replace")
    return output or ""


def run_ebmc(command: tuple[str, ...], timeout_s: float, log: Path) -> EbmcRun:
    """Run one EBMC command; write its combined output to `log`.

    CPU time is the RUSAGE_CHILDREN delta, so calls must not run concurrently
    within one Python process.
    """
    cpu_before = children_cpu_s()
    start = time.perf_counter()
    try:
        completed = subprocess.run(command, capture_output=True, timeout=timeout_s)
        exit_code: int | None = completed.returncode
        output = decode(completed.stdout) + decode(completed.stderr)
    except subprocess.TimeoutExpired as expired:
        exit_code = None
        output = decode(expired.stdout) + decode(expired.stderr) + f"\n[timeout after {timeout_s}s]\n"
    wall_s = time.perf_counter() - start
    log.write_text(output)
    results = {match["id"]: match["status"] for match in RESULT_LINE.finditer(output)}
    return EbmcRun(command, exit_code, wall_s, children_cpu_s() - cpu_before, results)
