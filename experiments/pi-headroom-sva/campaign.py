"""Four-hour, two-worker Pi/Headroom/EBMC campaign orchestrator."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from core import (
    EBMC,
    ROOT,
    SKILL,
    Pause,
    State,
    atomic_json,
    closure,
    digest,
    inventory,
    read_json,
)
from verifier import Verifier


def initialize(state: State, cfg: dict):
    tasks = inventory()
    if cfg.get("task"):
        tasks = [t for t in tasks if t["id"] == cfg["task"]]
        if not tasks:
            raise Pause("Unknown task: " + cfg["task"])
    inputs = [
        ROOT / "config.json",
        ROOT / "package-lock.json",
        ROOT / "uv.lock",
        ROOT / "pi-extension.ts",
        ROOT / "campaign.py",
        ROOT / "core.py",
        ROOT / "verifier.py",
        ROOT / "tool_backend.py",
        SKILL / "SKILL.md",
        EBMC,
        *[Path(t["source"]) for t in tasks],
    ]
    state.initialize(inputs, cfg)
    atomic_json(state.root / "inventory.json", {"config": cfg, "tasks": tasks})
    return tasks


def direct(task, cfg, run_root):
    return Verifier(cfg).run(
        task, {}, "target", [], "k-induction", run_root / "tasks" / task["id"]
    )


async def rpc_agent(task, cfg, run_root, seconds):
    session_dir = run_root / "tasks" / task["id"] / "pi-session"
    session_dir.mkdir(parents=True, exist_ok=True)
    workspace = run_root / "tasks" / task["id"] / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    shutil.copy2(task["source"], workspace / Path(task["source"]).name)
    system = (
        (SKILL / "SKILL.md").read_text()
        + f"""\n\nYou are proving exactly one benchmark. Read the task first.
You have ordinary shell, read, write, edit, and search tools, plus optional proof-bookkeeping tools.
Choose your own proof strategy, induction depth, bounded depth, engine, solver, scripts, and harnesses.
Bounded filtering is optional. The structured helper expression interface is a convenience, not a restriction on experiments.
Work in {workspace}. Preserve the benchmark source, original target, and supplied premises.
Use custom files for arbitrary SVA, helper state, cutpoints, blackboxing, abstractions, and other transformations.
Read {SKILL / "references/recording.md"} and use the run recorder for custom verifier commands.
For a custom proof, save proof-ledger.json and a replay script in the workspace, with preservation obligations and complete evidence.
Custom results require semantic review; the automated campaign only classifies structured verifier results.
Only completed unbounded proofs discharge obligations. Prove generated assumptions before using them and keep dependencies acyclic.
Your remaining task budget is {seconds:.1f} seconds. Per-call timeouts are selectable within that budget.
Finish with the original target's proof and evidence, or an explicit account of unresolved obligations.
"""
    )
    env = {
        **os.environ,
        "PI_CODING_AGENT_DIR": str(ROOT / "pi-config"),
        "PI_CODING_AGENT_SESSION_DIR": str(session_dir),
        "PI_OFFLINE": "1",
        "PI_SKIP_VERSION_CHECK": "1",
        "PI_TELEMETRY": "0",
        "SVA_RUN_ROOT": str(run_root),
        "SVA_TASK_ID": task["id"],
        "SVA_TASK_DEADLINE": str(time.time() + seconds),
    }
    cmd = [
        str(ROOT / "node_modules/.bin/pi"),
        "--mode",
        "rpc",
        "--provider",
        "openrouter",
        "--model",
        cfg["model"],
        "--session-dir",
        str(session_dir),
        "-e",
        str(ROOT / "pi-extension.ts"),
        "--no-context-files",
        "--system-prompt",
        system,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=workspace,
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
        limit=32 * 1024 * 1024,
    )
    transcript = run_root / "tasks" / task["id"] / "pi-rpc.jsonl"
    errfile = run_root / "tasks" / task["id"] / "pi-stderr.log"
    prompt = {
        "id": "prompt-1",
        "type": "prompt",
        "message": "Begin this proof task. Record hypotheses and verifier evidence. Stop after a completed target proof or when useful options are exhausted.",
    }
    proc.stdin.write(
        (
            json.dumps({"type": "set_auto_compaction", "enabled": False})
            + "\n"
            + json.dumps(prompt)
            + "\n"
        ).encode()
    )
    await proc.stdin.drain()
    deadline = time.monotonic() + seconds
    records = []
    try:
        while time.monotonic() < deadline:
            line = await asyncio.wait_for(
                proc.stdout.readline(), timeout=max(0.1, deadline - time.monotonic())
            )
            if not line:
                break
            records.append(line.decode(errors="replace"))
            with transcript.open("a") as stream:
                stream.write(records[-1])
            event = json.loads(line)
            if event.get("type") == "agent_settled" or (
                event.get("type") == "agent_end" and not event.get("willRetry")
            ):
                break
    except (asyncio.TimeoutError, json.JSONDecodeError):
        pass
    finally:
        if proc.returncode is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(proc.wait(), 5)
            except asyncio.TimeoutError:
                os.killpg(proc.pid, signal.SIGKILL)
                await proc.wait()
        transcript.write_text("".join(records))
        errfile.write_bytes(await proc.stderr.read())
    return {
        "exit_code": proc.returncode,
        "transcript": str(transcript),
        "workspace": str(workspace),
        "custom_proof_review_required": (workspace / "proof-ledger.json").exists(),
    }


def best_target_run(run_root, task_id):
    p = run_root / "tasks" / task_id / "candidates.json"
    if not p.exists():
        return None, None
    data = read_json(p)
    proved = [
        r
        for r in data["runs"]
        if r["obligation"] == "target" and r["outcome"] == "proved"
    ]
    return (proved[-1] if proved else None), data


def proof_fields(run_result, task_dir, locator):
    run_file = Path(run_result["run"]) / "run.json"
    record = read_json(run_file)
    ev = run_result["evidence"]
    return {
        "proof_kind": "unbounded",
        "run": str(run_file.relative_to(task_dir)),
        "run_sha256": digest(run_file),
        "evidence": {"file": ev, "sha256": record["evidence"][ev], "locator": locator},
        "context_review": "Exact property ID, top, clock/reset, source/config hashes, premises, engine mode, and dependency contexts reviewed by campaign adapter.",
    }


def audit_replay(task, task_dir, candidates, deps, replay):
    required = []
    for dep in deps:
        required.extend(closure(candidates, dep))
    required = list(dict.fromkeys(required))
    obligations = []
    for cid in required:
        choices = [
            r
            for r in read_json(task_dir / "candidates.json")["runs"]
            if r["obligation"] == cid
            and r["outcome"] == "proved"
            and r["mode"] in ("k-induction", "ic3", "bdd")
        ]
        if not choices:
            raise Pause(f"{task['id']}: missing proved helper evidence for {cid}")
        r = choices[-1]
        c = candidates[cid]
        node = {
            "id": cid,
            "statement": c["expression"],
            "scope": task["top"],
            "dependencies": c["dependencies"],
            "premises": [p["id"] for p in task["premises"]],
            "outcome": "proved",
        }
        node.update(
            proof_fields(
                r, task_dir, r["property_identifier"] + " status PROVED with proof_via"
            )
        )
        obligations.append(node)
    target = {
        "id": "target",
        "statement": task["target"],
        "scope": task["top"],
        "dependencies": deps,
        "premises": [p["id"] for p in task["premises"]],
        "outcome": "proved",
    }
    target.update(
        proof_fields(
            replay,
            task_dir,
            replay["property_identifier"] + " status PROVED with proof_via",
        )
    )
    ledger = {
        "schema_version": 1,
        "target": "target",
        "premises": task["premises"],
        "obligations": obligations + [target],
        "transformations": [],
    }
    for parent, parent_deps in [("target", deps)] + [
        (cid, candidates[cid]["dependencies"]) for cid in required
    ]:
        for dep in parent_deps:
            ledger["transformations"].append(
                {
                    "id": "use_" + parent + "_" + dep,
                    "kind": "proved_helper_assumption",
                    "description": "Use independently proved helper "
                    + dep
                    + " while proving "
                    + parent
                    + ".",
                    "applies_to": [parent],
                    "obligations": [dep],
                }
            )
    ledger_path = task_dir / "proof-ledger.json"
    atomic_json(ledger_path, ledger)
    audit = subprocess.run(
        [sys.executable, str(SKILL / "scripts/audit_proof.py"), str(ledger_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    parsed = json.loads(audit.stdout)
    atomic_json(task_dir / "audit.json", parsed)
    return parsed


async def campaign_task(task, cfg, state, run_root):
    started = time.monotonic()
    state.event("task_start", task=task["id"])
    first = await asyncio.to_thread(direct, task, cfg, run_root)
    result = {"task": task["id"], "direct": first, "outcome": first["outcome"]}
    if first["outcome"] in ("timeout", "induction_failure", "unknown"):
        remaining = max(
            0,
            min(
                cfg["task_seconds"] - (time.monotonic() - started),
                state.snapshot()["discovery_deadline"] - time.time(),
            ),
        )
        if time.time() < state.snapshot()["discovery_deadline"] and remaining > 1:
            result["pi"] = await rpc_agent(task, cfg, run_root, remaining)
    target, _ = best_target_run(run_root, task["id"])
    result["candidate_target"] = target
    result["discovery_seconds"] = time.monotonic() - started
    with state.transaction() as s:
        s["tasks"][task["id"]] = result
        s["last_operation_at"] = time.time()


async def run_campaign(tasks, cfg, state, run_root):
    if not os.getenv("OPENROUTER_API_KEY"):
        raise Pause("missing OPENROUTER_API_KEY")
    state.start()
    sem = asyncio.Semaphore(cfg["workers"])

    async def guarded(t):
        async with sem:
            if (
                time.time() + cfg["verifier_seconds"]
                < state.snapshot()["discovery_deadline"]
            ):
                await campaign_task(t, cfg, state, run_root)

    completed = state.snapshot()["tasks"]
    await asyncio.gather(*(guarded(t) for t in tasks if t["id"] not in completed))

    async def replay_one(task):
        async with sem:
            snap = state.snapshot()["tasks"].get(task["id"])
            if (
                not snap
                or time.time() + cfg["verifier_seconds"] >= state.snapshot()["deadline"]
            ):
                return
            candidate = snap.get("candidate_target")
            deps = candidate["dependencies"] if candidate else []
            if snap["direct"]["outcome"] != "proved" and not candidate:
                return
            p = run_root / "tasks" / task["id"] / "candidates.json"
            data = read_json(p) if p.exists() else {"candidates": {}}
            replay_mode = candidate["mode"] if candidate else snap["direct"]["mode"]
            replay_settings = candidate or snap["direct"]
            replay = await asyncio.to_thread(
                Verifier(cfg).run,
                task,
                data["candidates"],
                "target",
                deps,
                replay_mode,
                run_root / "tasks" / task["id"],
                bound=replay_settings.get("bound"),
                timeout_seconds=replay_settings.get("timeout_seconds"),
            )
            audit = {
                "bookkeeping_ok": False,
                "errors": ["replay was not an unbounded proof"],
            }
            if replay["outcome"] == "proved":
                audit = await asyncio.to_thread(
                    audit_replay,
                    task,
                    run_root / "tasks" / task["id"],
                    data["candidates"],
                    deps,
                    replay,
                )
            with state.transaction() as s:
                s["tasks"][task["id"]]["replay"] = replay
                s["tasks"][task["id"]]["audit"] = audit
                s["tasks"][task["id"]]["outcome"] = (
                    "proved"
                    if replay["outcome"] == "proved" and audit.get("bookkeeping_ok")
                    else replay["outcome"]
                )

    await asyncio.gather(*(replay_one(t) for t in tasks))
    with state.transaction() as s:
        s["status"] = "completed"
        s["last_operation_at"] = time.time()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["prepare", "run"])
    ap.add_argument("--run-root", type=Path, default=ROOT / "runs/campaign")
    ap.add_argument("--config", type=Path, default=ROOT / "config.json")
    args = ap.parse_args()
    cfg = read_json(args.config)
    state = State(args.run_root)
    try:
        tasks = initialize(state, cfg)
        if args.command == "prepare":
            print(
                json.dumps(
                    {
                        "status": "prepared",
                        "tasks": len(tasks),
                        "credential_present": bool(os.getenv("OPENROUTER_API_KEY")),
                    }
                )
            )
            return 0
        asyncio.run(run_campaign(tasks, cfg, state, args.run_root.resolve()))
        print(json.dumps({"status": "completed"}))
        return 0
    except Pause as exc:
        state.event("paused", reason=str(exc))
        with state.transaction() as s:
            s["status"] = "paused"
            s["pause_reason"] = str(exc)
            s["last_operation_at"] = time.time()
        print(json.dumps({"status": "paused", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
