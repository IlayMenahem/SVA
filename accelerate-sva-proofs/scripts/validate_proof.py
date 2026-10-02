#!/usr/bin/env python3
"""Accept a proof only if its ledger audits and one clean replay proves the closure."""

import argparse
import json
import sys
from pathlib import Path

from audit_proof import audit, audit_run, ids, indexed, require, text_field
from proof_io import contained_file, load_json, resolve


def replay_results(replay, base):
    run_dir = resolve(base, text_field(replay, "run")).parent
    results = load_json(contained_file(run_dir, text_field(replay["evidence"], "file")))
    require(isinstance(results, dict), "replay results must be an object")
    return indexed(results.get("properties"), "replay property")


def check_obligation(node, result):
    name = node["id"]
    require(result.get("kind") == "assert", f"{name}: replayed as {result.get('kind')}")
    require(result.get("status") == "proven", f"{name}: replay status {result.get('status')}")
    text_field(result, "engine")
    assumed = set(ids(result.get("assumed"), f"{name} assumed"))
    allowed = set(node["dependencies"]) | set(node["premises"])
    require(assumed <= allowed, f"{name}: undeclared assumptions {sorted(assumed - allowed)}")


def check_cover(name, result):
    require(result is not None, f"cover not replayed: {name}")
    require(result.get("kind") == "cover", f"{name}: replayed as {result.get('kind')}")
    require(result.get("status") == "covered", f"{name}: cover status {result.get('status')}")


def validate(path):
    audit_result = audit(path)
    errors = list(audit_result["errors"])
    try:
        ledger = load_json(path)
        replay = ledger.get("replay")
        require(isinstance(replay, dict), "missing replay entry")
        base = Path(path).resolve().parent
        audit_run(replay, base)
        results = replay_results(replay, base)
        nodes = indexed(ledger["obligations"], "obligation")
        covers = ids(replay.get("covers"), "replay covers")
        require(bool(covers), "replay needs at least one nonvacuity cover")
        for name in audit_result.get("closure", []):
            try:
                require(name in results, f"obligation not replayed: {name}")
                check_obligation(nodes[name], results[name])
            except ValueError as exc:
                errors.append(str(exc))
        for name in covers:
            try:
                check_cover(name, results.get(name))
            except ValueError as exc:
                errors.append(str(exc))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors.append(f"replay: {exc}")
    return {
        "accepted": not errors,
        "formal_validity": "not_certified",
        "target": audit_result.get("target"),
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger")
    args = parser.parse_args()
    try:
        result = validate(args.ledger)
    except (OSError, ValueError, TypeError) as exc:
        result = {"accepted": False, "formal_validity": "not_certified", "errors": [str(exc)]}
    print(json.dumps(result, indent=2))
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
