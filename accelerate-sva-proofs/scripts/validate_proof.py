#!/usr/bin/env python3
"""Accept a proof only if the ledger's DAG is valid and one clean replay proves its closure."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from audit_proof import Json, audit_run, check_dag, ids, indexed, require, text_field
from proof_io import contained_file, load_json, resolve


def replay_results(replay: Json, base: Path) -> dict[str, Json]:
    run_dir = resolve(base, text_field(replay, "run")).parent
    results = load_json(contained_file(run_dir, text_field(replay["evidence"], "file")))
    require(isinstance(results, dict), "replay results must be an object")
    return indexed(results.get("properties"), "replay property")


def check_obligation(name: str, node: Json, result: Json | None) -> None:
    require(result is not None, f"obligation not replayed: {name}")
    require(result.get("kind") == "assert", f"{name}: replayed as {result.get('kind')}")
    require(
        result.get("status") == "proven",
        f"{name}: replay status {result.get('status')}",
    )
    text_field(result, "engine")
    assumed = set(ids(result.get("assumed"), f"{name} assumed"))
    allowed = set(node["dependencies"]) | set(node["premises"])
    require(
        assumed <= allowed,
        f"{name}: undeclared assumptions {sorted(assumed - allowed)}",
    )


def check_cover(name: str, result: Json | None) -> None:
    require(result is not None, f"cover not replayed: {name}")
    require(result.get("kind") == "cover", f"{name}: replayed as {result.get('kind')}")
    require(
        result.get("status") == "covered",
        f"{name}: cover status {result.get('status')}",
    )


def failure(check: Callable[..., None], *args: Any) -> str | None:
    try:
        check(*args)
    except ValueError as exc:
        return str(exc)
    return None


def replay_errors(ledger: Any, base: Path) -> list[str]:
    dag = check_dag(ledger)
    replay = ledger.get("replay")
    require(isinstance(replay, dict), "missing replay entry")
    audit_run(replay, base)
    results = replay_results(replay, base)
    covers = ids(replay.get("covers"), "replay covers")
    require(bool(covers), "replay needs at least one nonvacuity cover")
    found = [
        failure(check_obligation, name, dag.nodes[name], results.get(name))
        for name in sorted(dag.closure)
    ]
    found += [failure(check_cover, name, results.get(name)) for name in covers]
    return [error for error in found if error]


def validate(path: str | Path) -> Json:
    try:
        errors = replay_errors(load_json(path), Path(path).resolve().parent)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors = [str(exc)]
    return {
        "accepted": not errors,
        "formal_validity": "not_certified",
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger")
    result = validate(parser.parse_args().ledger)
    print(json.dumps(result, indent=2))
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
