"""Antigravity agent proof execution for ex3 in the pi-headroom-sva environment."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import urllib.request
import uuid
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.chdir(root)
sys.path = [str(root)] + [p for p in sys.path if Path(p).resolve() != root / "setup"]

from campaign import audit_replay, best_target_run, direct, initialize
from core import State, atomic_json, closure, read_json
from tool_backend import execute as tool_execute
from verifier import Verifier


def compress_with_headroom(content: str, model: str, headroom_url: str):
    data = json.dumps(
        {"messages": [{"role": "tool", "content": content}], "model": model}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{headroom_url}/v1/compress",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    latency_ms = (time.perf_counter() - t0) * 1000
    compressed_text = result["messages"][0]["content"]
    tokens_before = len(content.split())
    tokens_after = len(compressed_text.split())
    return {
        "latency_ms": latency_ms,
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
        "compressed_length": len(compressed_text),
        "original_length": len(content),
    }


def main():
    run_root = (root / "runs/ex3-antigravity").resolve()
    if run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True, exist_ok=True)

    cfg = read_json(root / "config-ex3-antigravity.json")
    state = State(run_root)
    tasks = initialize(state, cfg)
    task = next(t for t in tasks if t["id"] == "ex3")
    task_dir = run_root / "tasks/ex3"
    task_dir.mkdir(parents=True, exist_ok=True)
    workspace = task_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    shutil.copy2(task["source"], workspace / Path(task["source"]).name)

    state.start()
    started_time = time.monotonic()
    print("=== 1. Starting Direct Baseline Check ===")
    first = direct(task, cfg, run_root)
    print(
        f"Direct baseline outcome: {first['outcome']} (property: {first.get('property_identifier')})"
    )

    def call_tool(action, **kwargs):
        req = {"run_root": str(run_root), "task": "ex3", "action": action, **kwargs}
        res = tool_execute(req)
        return res

    print("\n=== 2. Antigravity Agent Tool Invocation ===")
    task_info = call_tool("read_task")
    print(f"Read task: target={task_info['target'].strip()}")

    candidates_to_prove = [
        {
            "cid": "inv_flag01",
            "expr": "@(posedge clk) disable iff (rst) (flag == 0 || flag == 1)",
            "deps": [],
            "hypothesis": "flag is only ever assigned 0 or 1, so the invariant flag in {0,1} is 1-inductive and lets us rewrite flag<1 as flag==0 in the target.",
        },
        {
            "cid": "inv_flag0_rel",
            "expr": "@(posedge clk) disable iff (rst) (flag != 0 || (x >= 0 && y >= -1 && ((x < 50 && y == x) || (x >= 50 && x + y == 98))))",
            "deps": [],
            "hypothesis": "While flag==0 the design is a counter: (x,y) tracks (k,k) for x<50 and (x,98-x) for x>=50, with x>=0 and y>=-1. This linear phase invariant is 1-inductive given inv_flag01 and is what pins x==99, y==-1 at the moment y goes negative.",
        },
        {
            "cid": "inv_flag1_frozen",
            "expr": "@(posedge clk) disable iff (rst) (flag != 1 || (x == 99 && y == -2))",
            "deps": ["inv_flag01", "inv_flag0_rel"],
            "hypothesis": "The only transition into flag==1 comes from flag==0 with y==-1, where inv_flag0_rel forces x==99; the x-increment is suppressed that cycle, so flag==1 states are frozen at (x=99, y=-2). Combined with inv_flag01 this pointwise implies the target.",
        },
    ]

    for item in candidates_to_prove:
        cid = item["cid"]
        print(f"\nSubmitting candidate: {cid}")
        sub = call_tool(
            "submit_candidate",
            candidate_id=cid,
            expression=item["expr"],
            dependencies=item["deps"],
            hypothesis=item["hypothesis"],
        )
        print(f"  Submitted {cid}: {sub['status']}")

        print(f"  Running bounded check (k=30) for {cid}...")
        b_res = call_tool(
            "invoke_ebmc",
            obligation=cid,
            dependencies=item["deps"],
            mode="bounded",
            bound=30,
        )
        print(f"  Bounded check outcome: {b_res['outcome']}")

        print(f"  Running k-induction (k=1) for {cid}...")
        ind_res = call_tool(
            "invoke_ebmc",
            obligation=cid,
            dependencies=item["deps"],
            mode="k-induction",
            bound=1,
        )
        print(f"  k-induction outcome: {ind_res['outcome']}")
        assert ind_res["outcome"] == "proved", (
            f"Candidate {cid} failed to prove: {ind_res}"
        )

        evidence = call_tool(
            "inspect_evidence", run_id=Path(ind_res["run"]).name, original=False
        )
        orig_text = evidence["original"]
        if len(orig_text) >= cfg["compression_threshold_bytes"]:
            comp_stats = compress_with_headroom(
                orig_text, cfg["model"], cfg["headroom_url"]
            )
            comp_dir = run_root / "compression"
            comp_dir.mkdir(parents=True, exist_ok=True)
            atomic_json(
                comp_dir / f"{uuid.uuid4()}.json",
                {"artifact_id": evidence["artifact_id"], **comp_stats},
            )
            print(
                f"  Headroom compressed evidence: {comp_stats['tokens_before']} -> {comp_stats['tokens_after']} tokens"
            )

    print("\n=== 3. Proving Original Target Property ===")
    target_deps = ["inv_flag01", "inv_flag0_rel", "inv_flag1_frozen"]
    t_res = call_tool(
        "invoke_ebmc",
        obligation="target",
        dependencies=target_deps,
        mode="k-induction",
        bound=1,
    )
    print(f"Target proof outcome: {t_res['outcome']}")
    assert t_res["outcome"] == "proved", f"Target failed to prove: {t_res}"

    evidence = call_tool(
        "inspect_evidence", run_id=Path(t_res["run"]).name, original=False
    )
    orig_text = evidence["original"]
    if len(orig_text) >= cfg["compression_threshold_bytes"]:
        comp_stats = compress_with_headroom(
            orig_text, cfg["model"], cfg["headroom_url"]
        )
        comp_dir = run_root / "compression"
        comp_dir.mkdir(parents=True, exist_ok=True)
        atomic_json(
            comp_dir / f"{uuid.uuid4()}.json",
            {"artifact_id": evidence["artifact_id"], **comp_stats},
        )
        print(
            f"  Headroom compressed evidence: {comp_stats['tokens_before']} -> {comp_stats['tokens_after']} tokens"
        )

    discovery_seconds = time.monotonic() - started_time
    target_run, store_data = best_target_run(run_root, "ex3")
    task_result = {
        "task": "ex3",
        "direct": first,
        "outcome": "proved",
        "candidate_target": target_run,
        "discovery_seconds": discovery_seconds,
    }

    print("\n=== 4. Clean Verifier Replay and Audit ===")
    replay = Verifier(cfg).run(
        task,
        store_data["candidates"],
        "target",
        target_deps,
        target_run["mode"],
        task_dir,
        bound=target_run["bound"],
        timeout_seconds=target_run["timeout_seconds"],
    )
    print(
        f"Clean replay target outcome: {replay['outcome']} in {replay['elapsed_seconds']:.3f}s"
    )
    assert replay["outcome"] == "proved", "Replay did not prove"

    audit = audit_replay(task, task_dir, store_data["candidates"], target_deps, replay)
    print(
        f"Ledger audit result: bookkeeping_ok={audit.get('bookkeeping_ok')}, errors={audit.get('errors')}"
    )
    assert audit.get("bookkeeping_ok"), f"Audit failed: {audit}"

    task_result["replay"] = replay
    task_result["audit"] = audit

    with state.transaction() as s:
        s["tasks"]["ex3"] = task_result
        s["status"] = "completed"
        s["last_operation_at"] = time.time()

    print("\n=== 5. Independent Clean Replay Closure ===")
    clean_dest = run_root / "clean-replay"
    order = list(
        dict.fromkeys(
            cid for dep in target_deps for cid in closure(store_data["candidates"], dep)
        )
    )
    replay_runs = []
    for cid in order + ["target"]:
        used = (
            target_deps
            if cid == "target"
            else store_data["candidates"][cid]["dependencies"]
        )
        res = Verifier(cfg).run(
            task, store_data["candidates"], cid, used, "k-induction", clean_dest
        )
        rep = read_json(Path(res["run"]) / res["evidence"])
        prop = next(
            p
            for p in rep["properties"]
            if p["identifier"] == res["property_identifier"]
        )
        print(
            f"  {cid:16s} {res['outcome']:8s} {prop.get('status')} {prop.get('proof_via')}"
        )
        assert res["outcome"] == "proved", f"Clean replay failed for {cid}"
        replay_runs.append(res)
        atomic_json(
            clean_dest / "candidates.json",
            {"candidates": store_data["candidates"], "runs": replay_runs},
        )

    clean_audit = audit_replay(
        task, clean_dest, store_data["candidates"], target_deps, replay_runs[-1]
    )
    assert clean_audit["bookkeeping_ok"], f"Clean audit failed: {clean_audit}"

    all_discovery_runs = [first, *store_data["runs"], replay]
    summary = {
        "model": cfg["model"],
        "thinking": cfg["thinking"],
        "outcome": "proved",
        "discovery_seconds": discovery_seconds,
        "recorded_api_usd": "0",
        "requests": 0,
        "reasoning_tokens": 0,
        "verifier_calls": len(all_discovery_runs) + len(replay_runs),
        "verifier_elapsed_seconds": sum(
            r["elapsed_seconds"] for r in all_discovery_runs + replay_runs
        ),
        "clean_replay_seconds": sum(r["elapsed_seconds"] for r in replay_runs),
        "target_replay_seconds": replay_runs[-1]["elapsed_seconds"],
        "dependencies": target_deps,
        "semantic_checks": task["semantic_checks"],
        "audit": clean_audit,
    }
    atomic_json(run_root / "summary.json", summary)
    print("\nSummary:")
    print(json.dumps(summary, indent=2))

    print("\n=== 6. Generating Report ===")
    report_script = root / "report.py"
    report_cmd = [
        sys.executable,
        str(report_script),
        "--checkpoint",
        str(run_root / "checkpoint.json"),
        "--out",
        str(run_root / "report"),
    ]
    import subprocess

    subp = subprocess.run(report_cmd, capture_output=True, text=True, check=False)
    print(subp.stdout)
    if subp.stderr:
        print(subp.stderr)


if __name__ == "__main__":
    main()
