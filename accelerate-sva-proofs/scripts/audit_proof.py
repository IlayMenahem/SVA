#!/usr/bin/env python3
"""Audit proof records and dependencies; does not certify formal validity."""

import argparse
import json
import math
from pathlib import Path
import sys

from proof_io import contained_file, digest, load_json, resolve


OUTCOMES = {"unproved", "proved", "failed", "timeout", "bounded", "unknown", "error"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text_field(obj, key):
    require(isinstance(obj.get(key), str) and bool(obj[key].strip()), f"missing text: {key}")
    return obj[key]


def ids(value, label):
    require(isinstance(value, list) and all(isinstance(x, str) and x for x in value),
            f"{label} must be a list of IDs")
    require(len(set(value)) == len(value), f"duplicate ID in {label}")
    return value


def indexed(value, label):
    require(isinstance(value, list), f"{label} must be a list")
    result = {}
    for item in value:
        require(isinstance(item, dict), f"{label} entry must be an object")
        name = text_field(item, "id")
        require(name not in result, f"duplicate {label} ID: {name}")
        result[name] = item
    return result


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def audit_run(node, base):
    run_path = resolve(base, text_field(node, "run"))
    require(digest(run_path) == text_field(node, "run_sha256"), "run record hash mismatch")
    run = load_json(run_path)
    require(isinstance(run, dict) and run.get("schema_version") == 1, "invalid run schema")
    require(run.get("status") == "completed" and type(run.get("exit_code")) is int
            and run["exit_code"] == 0, "proved obligation lacks successful completed execution")
    require(run.get("errors") == [], "run contains recording errors")
    command = run.get("command")
    require(isinstance(command, list) and bool(command)
            and all(isinstance(arg, str) for arg in command) and bool(command[0]),
            "missing replay command")
    text_field(run, "tool_version")
    before, after = run.get("inputs_before"), run.get("inputs_after")
    require(isinstance(before, dict) and bool(before), "missing input fingerprints")
    require(before == after and run.get("inputs_unchanged") is True, "inputs changed during run")
    cwd = Path(text_field(run, "cwd"))
    require(cwd.is_absolute(), "run cwd must be absolute")
    manifest = run.get("manifest")
    require(isinstance(manifest, dict), "missing manifest")
    paths = ids(manifest.get("files"), "manifest files")
    require({str(resolve(cwd, p)) for p in paths} == set(before), "manifest/fingerprint mismatch")
    for path, expected in before.items():
        require(Path(path).is_absolute() and digest(path) == expected, f"stale input: {path}")
    evidence = run.get("evidence")
    require(isinstance(evidence, dict) and bool(evidence), "missing archived evidence")
    for name, expected in evidence.items():
        require(digest(contained_file(run_path.parent, name)) == expected,
                f"archived evidence hash mismatch: {name}")
    cited = node.get("evidence")
    require(isinstance(cited, dict), "missing interpreted proof evidence")
    name = text_field(cited, "file")
    require(name in evidence and evidence[name] == text_field(cited, "sha256"),
            "cited evidence hash mismatch")
    require(contained_file(run_path.parent, name).stat().st_size > 0, "cited evidence is empty")
    text_field(cited, "locator")
    text_field(node, "context_review")
    require(node.get("proof_kind") == "unbounded", "proof_kind must be unbounded")
    start, end = run.get("started_at"), run.get("finished_at")
    require(finite_number(start) and finite_number(end) and end >= start, "invalid run timestamps")
    return start, end


def audit(path):
    ledger = load_json(path)
    require(isinstance(ledger, dict) and ledger.get("schema_version") == 1, "invalid ledger schema")
    nodes = indexed(ledger.get("obligations"), "obligation")
    premises = indexed(ledger.get("premises"), "premise")
    transformations = indexed(ledger.get("transformations"), "transformation")
    require(not set(nodes) & set(premises), "obligation and premise IDs must be disjoint")
    target = text_field(ledger, "target")
    require(target in nodes, "target is not an obligation")
    for premise in premises.values():
        for key in ("statement", "source", "scope"):
            text_field(premise, key)
        require(premise.get("kind") == "supplied", "generated assumptions must be obligations")
    edges = {}
    for name, node in nodes.items():
        for key in ("statement", "scope"):
            text_field(node, key)
        require(isinstance(node.get("outcome"), str) and node["outcome"] in OUTCOMES,
                f"invalid outcome: {name}")
        edges[name] = set(ids(node.get("dependencies"), f"{name} dependencies"))
        require(edges[name] <= set(nodes), f"unknown obligation dependency: {name}")
        used = set(ids(node.get("premises"), f"{name} premises"))
        require(used <= set(premises), f"unknown supplied premise: {name}")
    for name, transformation in transformations.items():
        for key in ("kind", "description"):
            text_field(transformation, key)
        applied = ids(transformation.get("applies_to"), f"{name} applies_to")
        required = ids(transformation.get("obligations"), f"{name} obligations")
        require(bool(applied) and bool(required), f"transformation lacks uses or obligations: {name}")
        require(set(applied) <= set(nodes) and set(required) <= set(nodes),
                f"unknown transformation obligation or use: {name}")
        for use in applied:
            require(set(required) <= edges[use], f"missing transformation dependencies: {use}")
    # Iterative traversal avoids recursion limits for large DAGs.
    pending = {name: set(deps) for name, deps in edges.items()}
    order = []
    while pending:
        leaves = sorted(name for name, deps in pending.items() if not deps)
        require(bool(leaves), "dependency cycle")
        order.extend(leaves)
        for name in leaves:
            del pending[name]
        for deps in pending.values():
            deps.difference_update(leaves)
    closure, todo = set(), [target]
    while todo:
        name = todo.pop()
        if name not in closure:
            closure.add(name)
            todo.extend(edges[name])
    errors, times = [], {}
    for name in order:
        node = nodes[name]
        if node["outcome"] != "proved":
            if name in closure:
                errors.append(f"{name}: unresolved ({node['outcome']})")
            continue
        try:
            times[name] = audit_run(node, Path(path).resolve().parent)
            for dep in edges[name]:
                require(dep in times, f"dependency not supported by valid proved evidence: {dep}")
                require(times[dep][1] <= times[name][0], f"dependency not proved before parent run: {dep}")
        except (OSError, ValueError, TypeError) as exc:
            times.pop(name, None)
            errors.append(f"{name}: {exc}")
    return {"bookkeeping_ok": not errors, "formal_validity": "not_certified",
            "target": target, "closure": sorted(closure), "errors": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger")
    args = parser.parse_args()
    try:
        result = audit(args.ledger)
    except (OSError, ValueError, TypeError) as exc:
        result = {"bookkeeping_ok": False, "formal_validity": "not_certified", "errors": [str(exc)]}
    print(json.dumps(result, indent=2))
    return 0 if result["bookkeeping_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
