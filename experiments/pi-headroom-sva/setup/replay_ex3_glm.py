"""Replay GLM's entire dependency closure in fresh EBMC processes."""

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path = [str(root)] + [p for p in sys.path if Path(p).resolve() != root / "setup"]
from campaign import audit_replay
from core import atomic_json, closure, inventory, read_json
from verifier import Verifier

run = root / "runs/ex3-glm53-high-retry"
state = read_json(run / "checkpoint.json")
task = next(t for t in inventory() if t["id"] == "ex3")
original = read_json(run / "tasks/ex3/candidates.json")
candidates = original["candidates"]
deps = state["tasks"]["ex3"]["candidate_target"]["dependencies"]
dest = run / "clean-replay"
order = list(dict.fromkeys(cid for dep in deps for cid in closure(candidates, dep)))
runs = []
for cid in order + ["target"]:
    used = deps if cid == "target" else candidates[cid]["dependencies"]
    result = Verifier(state["config"]).run(
        task, candidates, cid, used, "k-induction", dest
    )
    report = read_json(Path(result["run"]) / result["evidence"])
    prop = next(
        p
        for p in report["properties"]
        if p["identifier"] == result["property_identifier"]
    )
    print(cid, result["outcome"], prop.get("status"), prop.get("proof_via"))
    if result["outcome"] != "proved":
        raise SystemExit("Clean replay failed")
    runs.append(result)
    atomic_json(dest / "candidates.json", {"candidates": candidates, "runs": runs})
audit = audit_replay(task, dest, candidates, deps, runs[-1])
if not audit["bookkeeping_ok"]:
    raise SystemExit(str(audit))
discovery_runs = [
    state["tasks"]["ex3"]["direct"],
    *original["runs"],
    state["tasks"]["ex3"]["replay"],
]
summary = {
    "model": state["config"]["model"],
    "thinking": state["config"]["thinking"],
    "outcome": "proved",
    "discovery_seconds": state["tasks"]["ex3"]["discovery_seconds"],
    "recorded_api_usd": state["spent_usd"],
    "requests": len(state["charges"]),
    "reasoning_tokens": sum(c["usage"].get("reasoning", 0) for c in state["charges"]),
    "verifier_calls": len(discovery_runs) + len(runs),
    "verifier_elapsed_seconds": sum(
        r["elapsed_seconds"] for r in discovery_runs + runs
    ),
    "clean_replay_seconds": sum(r["elapsed_seconds"] for r in runs),
    "target_replay_seconds": runs[-1]["elapsed_seconds"],
    "dependencies": deps,
    "semantic_checks": task["semantic_checks"],
    "audit": audit,
}
atomic_json(run / "summary.json", summary)
print(summary)
