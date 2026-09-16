"""EBMC adapter that records complete, property-specific proof evidence."""

from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from core import EBMC, SKILL, atomic_json, parse_result


def safe_name(value: str) -> str:
    if not value or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
        for c in value
    ):
        raise ValueError(
            "identifier must contain only letters, digits, and underscores"
        )
    return value


def materialize(
    task: dict, candidates: dict, obligation: str, dependencies: list[str], output: Path
) -> str:
    source = Path(task["source"]).read_text()
    declarations = []
    needed = set(dependencies)
    if obligation != "target":
        needed.add(obligation)
    for cid in sorted(needed):
        c = candidates[cid]
        safe_name(cid)
        declarations.append(
            f"\nproperty sva_{cid};\n  {c['expression']}\nendproperty\n"
        )
    directives = [f"assume property(sva_{safe_name(d)});" for d in dependencies]
    assertion = (
        "assert property(prop);"
        if obligation == "target"
        else f"assert property(sva_{safe_name(obligation)});"
    )
    injected = (
        "".join(declarations) + "\n" + "\n".join(directives + [assertion]) + "\n\n"
    )
    rendered = (
        source[: task["insert_offset"]] + injected + source[task["insert_offset"] :]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered)
    return assertion


class Verifier:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    def run(
        self,
        task: dict,
        candidates: dict,
        obligation: str,
        dependencies: list[str],
        mode: str,
        task_dir: Path,
        *,
        bound=None,
        timeout_seconds=None,
    ):
        if mode not in ("bounded", "k-induction", "ic3", "bdd"):
            raise ValueError("unsupported mode")
        if bound is not None and (type(bound) is not int or bound < 1):
            raise ValueError("bound must be a positive integer")
        if mode in ("ic3", "bdd") and bound is not None:
            raise ValueError("bound applies only to bounded checking or k-induction")
        if bound is None and mode in ("bounded", "k-induction"):
            bound = (
                self.cfg["filter_bound"]
                if mode == "bounded"
                else self.cfg["direct_induction_bound"]
            )
        timeout_seconds = (
            self.cfg["verifier_seconds"] if timeout_seconds is None else timeout_seconds
        )
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be finite and positive")
        stamp = f"{time.time_ns()}-{mode}"
        work = task_dir / "work" / stamp
        work.mkdir(parents=True)
        candidate = work / "candidate.sv"
        assertion = materialize(task, candidates, obligation, dependencies, candidate)
        manifest = work / "inputs.json"
        config_snapshot = work / "config.json"
        atomic_json(config_snapshot, self.cfg)
        atomic_json(
            manifest,
            {
                "files": [
                    str(candidate),
                    str(config_snapshot),
                    str(SKILL / "SKILL.md"),
                    str(EBMC),
                ],
                "settings": {
                    "top": task["top"],
                    "mode": mode,
                    "bound": bound,
                    "timeout_seconds": timeout_seconds,
                    "reset": f"{task['top']}.rst" if task["reset"] else None,
                    "assertion": assertion,
                    "dependencies": dependencies,
                },
            },
        )
        report = work / "result.json"
        run_dir = task_dir / "proof-runs" / stamp
        cmd = [
            str(EBMC),
            str(candidate),
            "--top",
            task["top"],
            "--json-result",
            str(report),
            "--trace",
        ]
        if task["reset"]:
            cmd += ["--reset", f"{task['top']}.rst"]
        if mode == "bounded":
            cmd += ["--bound", str(bound)]
        elif mode == "k-induction":
            cmd += ["--k-induction", "--bound", str(bound)]
        else:
            cmd += ["--" + mode]
        recorder = [
            sys.executable,
            str(SKILL / "scripts/record_run.py"),
            "--cwd",
            str(work),
            "--manifest",
            str(manifest),
            "--output",
            str(run_dir),
            "--timeout",
            str(timeout_seconds),
            "--tool-version",
            "EBMC 6.0 (ebmc-6.0)",
            "--report",
            str(report),
            "--",
            *cmd,
        ]
        proc = subprocess.Popen(
            recorder,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        old_handler = None
        if threading.current_thread() is threading.main_thread():

            def terminate(_signum, _frame):
                try:
                    os.killpg(proc.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass

            old_handler = signal.signal(signal.SIGTERM, terminate)
        try:
            proc.communicate()
        finally:
            if old_handler is not None:
                signal.signal(signal.SIGTERM, old_handler)
        run = (
            json.loads((run_dir / "run.json").read_text())
            if (run_dir / "run.json").exists()
            else {"status": "error", "errors": ["recorder failed"]}
        )
        parsed = {}
        if report.exists():
            try:
                parsed = json.loads(report.read_text())
            except json.JSONDecodeError:
                parsed = {}
        expected = f"Verilog::$root.{task['top']}.assert.{len(dependencies) + 1}"
        outcome = parse_result(parsed, expected, mode, run)
        evidence_rel = "reports/000-result.json"
        result = {
            "obligation": obligation,
            "dependencies": dependencies,
            "mode": mode,
            "bound": bound,
            "timeout_seconds": timeout_seconds,
            "outcome": outcome["outcome"],
            "property_identifier": expected,
            "run": str(run_dir),
            "elapsed_seconds": run.get("elapsed_seconds"),
            "run_status": run.get("status"),
            "evidence": evidence_rel,
            "candidate_source": str(candidate),
        }
        atomic_json(work / "classification.json", result)
        return result
