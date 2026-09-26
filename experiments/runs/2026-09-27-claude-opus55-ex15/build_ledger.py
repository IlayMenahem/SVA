"""Build proof-ledger.json for the WIDTH=32 ex15 proof from the recorded Jasper runs."""

import hashlib
import json
from pathlib import Path
from typing import Any

RUN_ROOT: Path = Path(__file__).resolve().parent
TARGET_SOURCE: str = "datasets/raw/large-lemma-miners/benchmarks/hard/ex15_ebmc.sv, property prop"
SCOPE: str = "ex15 (WIDTH=32) with bound checker ex15.u_obl; clock clk, reset rst (active high), disable iff (rst)"

OBLIGATIONS: dict[str, dict[str, Any]] = {
    "target": {
        "property": "ex15.u_obl.target",
        "statement": "@(posedge clk) disable iff (rst) (state != DONE || n <= 0 || m < n)",
        "dependencies": ["h_x_le_n", "h_m_lt_x"],
        "context": "assert target; assume h_x_le_n and h_m_lt_x (defines ASSERT_TARGET ASSUME_X_LE_N ASSUME_M_LT_X). "
        "EX15_PROPERTY lines list exactly these assert/assume properties plus cover c_done, which is covered in 5 cycles "
        "under the same assumptions (nonvacuity).",
    },
    "h_x_le_n": {
        "property": "ex15.u_obl.h_x_le_n",
        "statement": "@(posedge clk) disable iff (rst) (x <= n)",
        "dependencies": [],
        "context": "assert h_x_le_n only; no assumptions (EX15_PROPERTY lists a single assert).",
    },
    "h_m_lt_x": {
        "property": "ex15.u_obl.h_m_lt_x",
        "statement": "@(posedge clk) disable iff (rst) (m == 0 || m < x)",
        "dependencies": [],
        "context": "assert h_m_lt_x only; no assumptions (EX15_PROPERTY lists a single assert).",
    },
}

RUN_DIRS: dict[str, str] = {"target": "target-w32", "h_x_le_n": "x_le_n-w32", "h_m_lt_x": "m_lt_x-w32"}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def result_line(stdout: Path) -> str:
    return next(
        line for line in stdout.read_text().splitlines() if line.startswith("EX15_RESULT obl=")
    )


def ledger_entry(obligation_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    run_dir = Path("proof-runs") / RUN_DIRS[obligation_id]
    run_json = RUN_ROOT / run_dir / "run.json"
    evidence_hashes: dict[str, str] = json.loads(run_json.read_text())["evidence"]
    line = result_line(RUN_ROOT / run_dir / "stdout.log")
    assert "status=proven" in line, line
    return {
        "id": obligation_id,
        "statement": spec["statement"],
        "scope": SCOPE,
        "dependencies": spec["dependencies"],
        "premises": [],
        "outcome": "proved",
        "proof_kind": "unbounded",
        "run": str(run_dir / "run.json"),
        "run_sha256": sha256_of(run_json),
        "evidence": {
            "file": "stdout.log",
            "sha256": evidence_hashes["stdout.log"],
            "locator": f"{spec['property']}: '{line}' and the report -detailed 'Result : proven' block",
        },
        "context_review": f"JasperGold 2024.06p002, engines Hp Ht N B, WIDTH=32, clock clk, reset rst. {spec['context']}",
    }


def build_ledger() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "target": "target",
        "premises": [],
        "transformations": [],
        "obligations": [ledger_entry(obligation_id, spec) for obligation_id, spec in OBLIGATIONS.items()],
        "target_source": TARGET_SOURCE,
    }


if __name__ == "__main__":
    (RUN_ROOT / "proof-ledger.json").write_text(json.dumps(build_ledger(), indent=2) + "\n")
