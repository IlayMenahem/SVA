"""Stateful backend for the five controlled Pi tools."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from core import (
    EBMC,
    SKILL,
    State,
    atomic_json,
    closure,
    inventory,
    read_json,
    validate_expression,
)
from verifier import Verifier

ROOT = Path(__file__).resolve().parent
TASKS = {t["id"]: t for t in inventory()}


def store_path(root, task):
    return Path(root) / "tasks" / task / "candidates.json"


def load_store(root, task):
    p = store_path(root, task)
    return read_json(p) if p.exists() else {"candidates": {}, "runs": []}


def save_store(root, task, data):
    atomic_json(store_path(root, task), data)


def execute(req):
    root = Path(req["run_root"]).resolve()
    task_id = req.get("task")
    action = req["action"]
    if action == "reserve":
        State(root).reserve(req["request_id"], req["usd"])
        return {"ok": True}
    if action == "reconcile":
        State(root).reconcile(req["request_id"], req["usd"], req.get("usage", {}))
        return {"ok": True}
    if task_id not in TASKS:
        raise ValueError("unknown task")
    task = TASKS[task_id]
    data = load_store(root, task_id)
    if action == "read_task":
        cfg = State(root).snapshot().get("config", {})
        return {
            **task,
            "rtl": Path(task["source"]).read_text(),
            "workspace": str(root / "tasks" / task_id / "workspace"),
            "ebmc": str(EBMC),
            "skill_directory": str(SKILL),
            "run_recorder": str(SKILL / "scripts/record_run.py"),
            "verifier_defaults": {
                k: cfg.get(k)
                for k in ("filter_bound", "direct_induction_bound", "verifier_seconds")
            },
            "interface": "Shell and file tools are available. Structured helpers are optional; use custom files and recorded commands for other syntax, engines, solvers, or transformations. Custom proof results require semantic review before acceptance.",
        }
    if action == "submit_candidate":
        cid = req["candidate_id"]
        validate_expression(req["expression"])
        if len(cid) > 64 or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", cid):
            raise ValueError("invalid candidate id")
        if cid in data["candidates"]:
            raise ValueError("candidate id already exists")
        deps = list(dict.fromkeys(req.get("dependencies", [])))
        if any(d not in data["candidates"] for d in deps):
            raise ValueError("unknown dependency")
        data["candidates"][cid] = {
            "expression": req["expression"],
            "dependencies": deps,
            "includes_target": False,
            "hypothesis": req.get("hypothesis", ""),
            "retracted": False,
            "outcome": "unproved",
            "created_at": time.time(),
        }
        closure(data["candidates"], cid)
        save_store(root, task_id, data)
        return {"candidate_id": cid, "status": "unproved"}
    if action == "retract_candidate":
        cid = req["candidate_id"]
        if cid not in data["candidates"]:
            raise ValueError("unknown candidate")
        affected = {cid}
        changed = True
        while changed:
            changed = False
            for k, c in data["candidates"].items():
                if k not in affected and any(d in affected for d in c["dependencies"]):
                    affected.add(k)
                    changed = True
        for k in affected:
            data["candidates"][k]["retracted"] = True
            data["candidates"][k]["outcome"] = "unproved"
        save_store(root, task_id, data)
        return {"retracted": sorted(affected)}
    if action == "invoke_ebmc":
        obligation = req.get("obligation", "target")
        deps = list(dict.fromkeys(req.get("dependencies", [])))
        if obligation != "target" and obligation not in data["candidates"]:
            raise ValueError("unknown obligation")
        if (
            obligation != "target"
            and deps != data["candidates"][obligation]["dependencies"]
        ):
            raise ValueError(
                "invocation dependencies must exactly match the candidate record"
            )
        for d in deps:
            c = data["candidates"].get(d)
            if not c or c.get("retracted"):
                raise ValueError("missing or retracted dependency")
            if req["mode"] != "bounded" and c.get("outcome") != "proved":
                raise ValueError("unbounded parent requires proved dependencies")
        cfg = State(root).snapshot()["config"]
        timeout = req.get("timeout_seconds", cfg["verifier_seconds"])
        if os.getenv("SVA_TASK_DEADLINE"):
            remaining = float(os.environ["SVA_TASK_DEADLINE"]) - time.time()
            if remaining <= 0:
                raise ValueError("task time budget exhausted")
            timeout = min(timeout, remaining)
        result = Verifier(cfg).run(
            task,
            data["candidates"],
            obligation,
            deps,
            req["mode"],
            root / "tasks" / task_id,
            bound=req.get("bound"),
            timeout_seconds=timeout,
        )
        data["runs"].append(result)
        if obligation != "target":
            data["candidates"][obligation]["outcome"] = result["outcome"]
        save_store(root, task_id, data)
        return result
    if action == "inspect_evidence":
        artifact = req.get("artifact_id")
        run_id = req.get("run_id")
        artifact_file = None
        if artifact:
            run_id, sep, artifact_file = artifact.partition(":")
            if not sep:
                raise ValueError("artifact_id must be <run-id>:<relative-file>")
        if not run_id:
            raise ValueError("run_id or artifact_id is required")
        matches = [r for r in data["runs"] if Path(r["run"]).name == run_id]
        if len(matches) != 1:
            raise ValueError("unknown or ambiguous run id")
        r = matches[0]
        p = Path(r["run"]) / (artifact_file or req.get("file") or r["evidence"])
        if Path(r["run"]).resolve() not in p.resolve().parents:
            raise ValueError("evidence path escapes run")
        return {
            "classification": r,
            "artifact_id": run_id + ":" + str(p.relative_to(r["run"])),
            "original": p.read_text(),
        }
    raise ValueError("unknown action")


def main():
    try:
        print(json.dumps(execute(json.load(sys.stdin))))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
