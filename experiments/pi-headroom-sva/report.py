"""Generate JSON, CSV, and Markdown four-method comparisons."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from core import ROOT, inventory, read_json


def build(checkpoint=None):
    ours = (checkpoint or {}).get("tasks", {})
    rows = []
    for t in inventory():
        own = ours.get(t["id"], {})
        replay = own.get("replay", {})
        row = {
            "task": t["id"],
            "method_outcome": own.get("outcome", "missing"),
            "method_discovery_seconds": own.get("discovery_seconds"),
            "method_replay_seconds": replay.get("elapsed_seconds"),
            "semantic_checks": "reset reviewed; premise consistency and vacuity unresolved",
        }
        for m in ("ric3", "jasper", "vcf"):
            row[m + "_outcome"] = t["baselines"][m]["outcome"]
            row[m + "_seconds"] = t["baselines"][m]["seconds"]
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--checkpoint", type=Path, default=ROOT / "runs/campaign/checkpoint.json"
    )
    ap.add_argument("--out", type=Path, default=ROOT / "results")
    a = ap.parse_args()
    cp = read_json(a.checkpoint) if a.checkpoint.exists() else {}
    rows = build(cp)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "comparison.json").write_text(json.dumps(rows, indent=2) + "\n")
    with (a.out / "comparison.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    solved = {
        m: sum(r[m + "_outcome"] == "proved" for r in rows)
        for m in ("method", "ric3", "jasper", "vcf")
    }
    beyond = {
        m: [
            r["task"]
            for r in rows
            if r["method_outcome"] == "proved" and r[m + "_outcome"] != "proved"
        ]
        for m in ("ric3", "jasper", "vcf")
    }
    compressions = []
    if a.checkpoint.exists():
        for p in (a.checkpoint.parent / "compression").glob("*.json"):
            try:
                compressions.append(read_json(p))
            except (OSError, json.JSONDecodeError):
                pass
    providers = sorted(
        {
            c.get("usage", {}).get("openrouter_generation", {}).get("provider_name")
            for c in cp.get("charges", [])
            if c.get("usage", {}).get("openrouter_generation")
        }
    )
    md = [
        "# SVA campaign report",
        "",
        "## Status",
        "",
        f"Campaign status: `{cp.get('status', 'not run')}`. Method solves count only after clean replay and ledger audit.",
        "",
        "| Method | Solved |",
        "|---|---:|",
        *[f"| {m} | {n} |" for m, n in solved.items()],
        "",
        "## Tasks solved beyond published baselines",
        "",
    ]
    md += [f"- {m}: " + (", ".join(v) if v else "none") for m, v in beyond.items()]
    md += [
        "",
        "## Cost and compression",
        "",
        f"Reconciled API charges: `${cp.get('spent_usd', '0')}` across {len(cp.get('charges', []))} requests. Actual routed providers: {', '.join(providers) if providers else 'none recorded'}.",
        f"Headroom compressed {len(compressions)} evidence retrievals; recorded tokens: {sum(x.get('tokens_before', 0) for x in compressions)} before and {sum(x.get('tokens_after', 0) for x in compressions)} after.",
        "",
        "## Per-task outcomes",
        "",
        "| Task | Method | Discovery s | Replay s | rIC3 (s) | JasperGold (s) | VCF (s) |",
        "|---|---|---:|---:|---|---|---|",
    ]

    def cell(outcome, seconds):
        return f"{outcome} ({seconds:g})" if seconds is not None else outcome

    for r in rows:
        md.append(
            "| "
            + " | ".join(
                [
                    r["task"],
                    r["method_outcome"],
                    str(r["method_discovery_seconds"] or "—"),
                    str(r["method_replay_seconds"] or "—"),
                    cell(r["ric3_outcome"], r["ric3_seconds"]),
                    cell(r["jasper_outcome"], r["jasper_seconds"]),
                    cell(r["vcf_outcome"], r["vcf_seconds"]),
                ]
            )
            + " |"
        )
    md += [
        "",
        "## Runtime interpretation",
        "",
        "Method discovery time includes the direct EBMC attempt, model calls, compression, and exploratory verifier work. Replay time is reported separately. Published values are historical observations from Amazon EC2 m6i.32xlarge hardware; rIC3 and JasperGold used one-hour limits, while VCFormal includes longer carried-over limits. Tool versions: rIC3 authors’ paper build, JasperGold 2024.09, VCFormal 2024.09. Cross-machine speedups are not claimed.",
        "",
        "## Semantic checks",
        "",
        "Reset qualification is validated against EBMC 6.0. Complete premise-consistency and antecedent-reachability/vacuity checks remain explicitly unresolved per task.",
        "",
    ]
    (a.out / "REPORT.md").write_text("\n".join(md))
    print(json.dumps({"rows": len(rows), "solved_counts": solved, "beyond": beyond}))


if __name__ == "__main__":
    main()
