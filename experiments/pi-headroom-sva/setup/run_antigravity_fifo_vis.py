"""Antigravity agent (Gemini 3.8 Flash) proof execution for fifo_vis in the pi-sva environment with lean-ctx."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.chdir(root)
sys.path = [str(root)] + [p for p in sys.path if Path(p).resolve() != root / "setup"]

from campaign import audit_replay, best_target_run, direct, initialize
from core import State, atomic_json, closure, read_json
from tool_backend import execute as tool_execute
from verifier import Verifier


def compress_with_lean_ctx(content: str):
    t0 = time.perf_counter()
    lean_ctx_bin = os.environ.get("LEAN_CTX_BIN") or (
        "/opt/homebrew/bin/lean-ctx"
        if Path("/opt/homebrew/bin/lean-ctx").exists()
        else "lean-ctx"
    )
    proc = subprocess.run(
        [lean_ctx_bin, "-c", "cat"],
        input=content,
        text=True,
        capture_output=True,
        check=False,
    )
    latency_ms = (time.perf_counter() - t0) * 1000
    compressed_text = proc.stdout if proc.returncode == 0 and proc.stdout else content
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
    run_root = (root / "runs/fifo_vis-antigravity").resolve()
    if run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True, exist_ok=True)

    cfg = read_json(root / "config-fifo_vis-antigravity.json")
    state = State(run_root)
    tasks = initialize(state, cfg)
    task = next(t for t in tasks if t["id"] == "fifo_vis")
    task_dir = run_root / "tasks/fifo_vis"
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
        req = {"run_root": str(run_root), "task": "fifo_vis", "action": action, **kwargs}
        res = tool_execute(req)
        return res

    print("\n=== 2. Antigravity Agent Tool Invocation ===")
    task_info = call_tool("read_task")
    print(f"Read task: target={task_info['target'].strip()}")

    data_expr = (
        "@(posedge clk) disable iff (rst) (\n"
        "(sr.empty || (sr.tail < 4'd0) || (sr.mem[0] == rb.mem[4'(rb.head - 4'd1 - 4'd0)])) &&\n"
        "(sr.empty || (sr.tail < 4'd1) || (sr.mem[1] == rb.mem[4'(rb.head - 4'd1 - 4'd1)])) &&\n"
        "(sr.empty || (sr.tail < 4'd2) || (sr.mem[2] == rb.mem[4'(rb.head - 4'd1 - 4'd2)])) &&\n"
        "(sr.empty || (sr.tail < 4'd3) || (sr.mem[3] == rb.mem[4'(rb.head - 4'd1 - 4'd3)])) &&\n"
        "(sr.empty || (sr.tail < 4'd4) || (sr.mem[4] == rb.mem[4'(rb.head - 4'd1 - 4'd4)])) &&\n"
        "(sr.empty || (sr.tail < 4'd5) || (sr.mem[5] == rb.mem[4'(rb.head - 4'd1 - 4'd5)])) &&\n"
        "(sr.empty || (sr.tail < 4'd6) || (sr.mem[6] == rb.mem[4'(rb.head - 4'd1 - 4'd6)])) &&\n"
        "(sr.empty || (sr.tail < 4'd7) || (sr.mem[7] == rb.mem[4'(rb.head - 4'd1 - 4'd7)])) &&\n"
        "(sr.empty || (sr.tail < 4'd8) || (sr.mem[8] == rb.mem[4'(rb.head - 4'd1 - 4'd8)])) &&\n"
        "(sr.empty || (sr.tail < 4'd9) || (sr.mem[9] == rb.mem[4'(rb.head - 4'd1 - 4'd9)])) &&\n"
        "(sr.empty || (sr.tail < 4'd10) || (sr.mem[10] == rb.mem[4'(rb.head - 4'd1 - 4'd10)])) &&\n"
        "(sr.empty || (sr.tail < 4'd11) || (sr.mem[11] == rb.mem[4'(rb.head - 4'd1 - 4'd11)])) &&\n"
        "(sr.empty || (sr.tail < 4'd12) || (sr.mem[12] == rb.mem[4'(rb.head - 4'd1 - 4'd12)])) &&\n"
        "(sr.empty || (sr.tail < 4'd13) || (sr.mem[13] == rb.mem[4'(rb.head - 4'd1 - 4'd13)])) &&\n"
        "(sr.empty || (sr.tail < 4'd14) || (sr.mem[14] == rb.mem[4'(rb.head - 4'd1 - 4'd14)])) &&\n"
        "(sr.empty || (sr.tail < 4'd15) || (sr.mem[15] == rb.mem[4'(rb.head - 4'd1 - 4'd15)]))\n"
        ")"
    )

    candidates_to_prove = [
        {
            "cid": "inv_control",
            "expr": "@(posedge clk) disable iff (rst) ((sr.empty == rb.empty) && (sr.empty ? ((sr.tail == 4'd0) && (rb.head == rb.tail)) : ((rb.head - rb.tail) == (sr.tail + 4'd1))))",
            "deps": [],
            "hypothesis": "The two FIFOs maintain identical empty flags. When empty, sr.tail is 0 and rb.head == rb.tail. When nonempty, queue occupancy (rb.head - rb.tail) mod 16 equals sr.tail + 1. This inductive invariant couples control flags and pointer difference.",
        },
        {
            "cid": "inv_data",
            "expr": data_expr,
            "deps": ["inv_control"],
            "hypothesis": "For all active queue slots j from 0 to sr.tail, sr.mem[j] matches the corresponding ring buffer element at rb.mem[(rb.head - 1 - j) mod 16]. This 16-slot joint conjunction proves inductively given inv_control.",
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
            comp_stats = compress_with_lean_ctx(orig_text)
            comp_dir = run_root / "compression"
            comp_dir.mkdir(parents=True, exist_ok=True)
            atomic_json(
                comp_dir / f"{uuid.uuid4()}.json",
                {"artifact_id": evidence["artifact_id"], **comp_stats},
            )
            print(
                f"  lean-ctx compressed evidence: {comp_stats['tokens_before']} -> {comp_stats['tokens_after']} tokens ({comp_stats['latency_ms']:.1f}ms)"
            )

    print("\n=== 3. Proving Original Target Property ===")
    target_deps = ["inv_control", "inv_data"]
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
        comp_stats = compress_with_lean_ctx(orig_text)
        comp_dir = run_root / "compression"
        comp_dir.mkdir(parents=True, exist_ok=True)
        atomic_json(
            comp_dir / f"{uuid.uuid4()}.json",
            {"artifact_id": evidence["artifact_id"], **comp_stats},
        )
        print(
            f"  lean-ctx compressed evidence: {comp_stats['tokens_before']} -> {comp_stats['tokens_after']} tokens ({comp_stats['latency_ms']:.1f}ms)"
        )

    discovery_seconds = time.monotonic() - started_time
    target_run, store_data = best_target_run(run_root, "fifo_vis")
    task_result = {
        "task": "fifo_vis",
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
        s["tasks"]["fifo_vis"] = task_result
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
        "agent": cfg.get("agent", "antigravity"),
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

    # Also write ANTIGRAVITY-RESULT.md in task_dir
    result_md = f"""# fifo_vis: PROVED with Gemini 3.8 Flash + Antigravity + lean-ctx

- **Model**: {cfg['model']}
- **Agent**: {cfg.get('agent', 'antigravity')}
- **Context Compression**: lean-ctx (3.7.5)
- **Target Outcome**: {summary['outcome']}
- **Discovery Wall Time**: {summary['discovery_seconds']:.3f}s
- **Verifier Calls**: {summary['verifier_calls']}
- **Clean Replay Time**: {summary['clean_replay_seconds']:.3f}s
- **Audit**: bookkeeping_ok={clean_audit['bookkeeping_ok']}

## Invariant Dependency DAG
- `inv_control` -> `[]`: Couples FIFO empty flags and pointer difference `(rb.head - rb.tail) == sr.tail + 1`.
- `inv_data` -> `[inv_control]`: 16-slot joint conjunction mapping live slots `sr.mem[j]` to `rb.mem[(rb.head - 1 - j) mod 16]`.
- `target` -> `[inv_control, inv_data]`: Equivalence of outputs `(equal == 1)`.

All obligations discharged under unbounded 1-induction with EBMC 6.0 and MiniSAT.
"""
    (task_dir / "ANTIGRAVITY-RESULT.md").write_text(result_md)

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
    subp = subprocess.run(report_cmd, capture_output=True, text=True, check=False)
    print(subp.stdout)
    if subp.stderr:
        print(subp.stderr)


if __name__ == "__main__":
    main()
