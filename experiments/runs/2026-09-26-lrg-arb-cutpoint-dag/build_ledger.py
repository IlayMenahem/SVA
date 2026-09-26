"""Build proof-ledger.json for lrg_arb_lrg_N from gen.py's DAG and one recorded replay run.

Usage: python3 build_ledger.py N <run.json path relative to this dir>
Every obligation cites the replay's stdout.log line "RESULT <embedded>::<name> proven".
"""

import hashlib
import json
import pathlib
import sys

import gen

HERE: pathlib.Path = gen.HERE
SOURCE: str = "datasets/raw/large-lemma-miners/benchmarks/hard/lrg_arb_lrg_16_ebmc.sv"
SCOPE: str = ("main (lrg_arb_lrg_16_ebmc.sv, NUM_REQ={n}), clock clk, Jasper `reset rst` "
              "(reset held inactive after reset phase), assertions under disable iff(rst)-equivalent "
              "reset handling; {cut}")


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def level_of(n: int) -> dict[str, gen.Level]:
    return {name: lvl for lvl in gen.dag_levels(n) for name in lvl.asserts}


def result_name(name: str) -> str:
    return f"main.{name}" if name == gen.TARGET else name


def obligation_entry(n: int, name: str, ob: gen.Obligation, level: gen.Level,
                     run: str, run_sha: str, log_sha: str, log: str) -> dict[str, object]:
    locator: str = f"RESULT <embedded>::{result_name(name)} proven"
    proved: bool = locator in log
    cut: str = ("stopat chosen_priority (cutpoint: sound over-approximation)" if level.cut_cp
                else "concrete model, no cutpoint")
    return {
        "id": name,
        "statement": "prop (source line 91-94)" if name == gen.TARGET else f"assert property ({ob.expr})",
        "scope": SCOPE.format(n=n, cut=cut) + f"; Jasper session {level.name}",
        "dependencies": list(ob.deps),
        "premises": [],
        "outcome": "proved" if proved else "unknown",
        "run": run,
        "run_sha256": run_sha,
        "evidence": {"file": "stdout.log", "sha256": log_sha, "locator": locator},
        "proof_kind": "unbounded",
        "context_review": (f"Session {level.name} assumes exactly the listed dependencies "
                           f"({len(ob.deps)}) and no other constraint; "
                           + ("cp cut => result holds for every cp value, hence concretely."
                              if level.cut_cp else "proved on the uncut design.")),
    }


def transformations(n: int) -> list[dict[str, object]]:
    grant: list[dict[str, object]] = [{
        "id": f"cut_cp_grant_{i}",
        "kind": "cutpoint",
        "description": (f"stopat chosen_priority in Q_{i}_*: grant[{i}] is driven from a free cp; "
                        f"the cut relies on contract G_{i} (proved on the concrete design) to relate cp to ranks[{i}]."),
        "applies_to": [f"Q_{i}_{j}" for j in range(n) if j != i],
        "obligations": [f"G_{i}"],
    } for i in range(n)]
    minimal: list[dict[str, object]] = [{
        "id": f"cut_cp_min_{j}",
        "kind": "cutpoint",
        "description": (f"stopat chosen_priority in Q_*_{j}: the cut relies on contract M_{j} "
                        f"(proved on the concrete design) bounding cp by ranks[{j}] when {j} requests."),
        "applies_to": [f"Q_{i}_{j}" for i in range(n) if i != j],
        "obligations": [f"M_{j}"],
    } for j in range(n)]
    return grant + minimal


def main(argv: list[str]) -> None:
    n: int = int(argv[1])
    run: str = argv[2]
    run_path: pathlib.Path = HERE / run
    log: str = (run_path.parent / "stdout.log").read_text()
    run_sha: str = sha256(run_path)
    log_sha: str = sha256(run_path.parent / "stdout.log")
    levels: dict[str, gen.Level] = level_of(n)
    ledger: dict[str, object] = {
        "schema_version": 1,
        "target": gen.TARGET,
        "premises": [],
        "transformations": transformations(n),
        "obligations": [obligation_entry(n, name, ob, levels[name], run, run_sha, log_sha, log)
                        for name, ob in gen.all_obligations(n).items()],
        "harness_adaptation": (f"{SOURCE}: NUM_REQ overridden by elaborate -parameter; `int idx;` hoisted "
                               "to the top of the always_comb block (Verific VERI-1137, semantics-preserving); "
                               "`target: assert property (prop);` appended."),
    }
    (HERE / f"proof-ledger-N{n}.json").write_text(json.dumps(ledger, indent=2) + "\n")


if __name__ == "__main__":
    main(sys.argv)
