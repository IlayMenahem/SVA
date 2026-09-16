"""Durable experiment state, conservative report parsing, and exact task inventory."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import math
import os
import re
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
BENCH = REPO / "datasets/raw/large-lemma-miners/benchmarks/hard"
SKILL = REPO / "accelerate-sva-proofs"
EBMC = ROOT / "vendor/hw-cbmc/src/ebmc/ebmc"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with tmp.open("w") as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Pause(RuntimeError):
    pass


class State:
    def __init__(self, directory):
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "checkpoint.json"

    @contextlib.contextmanager
    def transaction(self):
        with (self.root / "checkpoint.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = read_json(self.path) if self.path.exists() else {}
            yield data
            atomic_json(self.path, data)

    def initialize(self, inputs, config):
        hashes = {str(Path(p).resolve()): digest(p) for p in inputs}
        with self.transaction() as s:
            if s:
                if s["inputs"] != hashes or s["config"] != config:
                    raise Pause("Resume input/config hashes changed")
                if time.time() < s["last_operation_at"]:
                    raise Pause("Wall clock moved backwards")
                return
            s.update(
                schema_version=1,
                inputs=hashes,
                config=config,
                started_at=None,
                deadline=None,
                discovery_deadline=None,
                last_operation_at=time.time(),
                spent_usd="0",
                reservations={},
                charges=[],
                tasks={},
                operations=[],
                status="prepared",
            )

    def start(self):
        with self.transaction() as s:
            if s["started_at"] is None:
                now = time.time()
                s.update(
                    started_at=now,
                    deadline=now + s["config"]["campaign_seconds"],
                    discovery_deadline=now
                    + s["config"]["campaign_seconds"]
                    - s["config"]["replay_reserve_seconds"],
                )
            s["status"] = "running"

    def snapshot(self):
        with self.transaction() as s:
            return json.loads(json.dumps(s))

    def event(self, kind, **fields):
        with self.transaction() as s:
            s["last_operation_at"] = time.time()
            s["operations"].append(dict(at=time.time(), kind=kind, **fields))

    def reserve(self, request_id, amount):
        amount = Decimal(str(amount))
        if not amount.is_finite() or amount <= 0:
            raise Pause("Invalid reservation")
        with self.transaction() as s:
            if request_id in s["reservations"] or any(
                c["id"] == request_id for c in s["charges"]
            ):
                raise Pause("Duplicate request ID")
            total = Decimal(s["spent_usd"]) + sum(
                (Decimal(r["usd"]) for r in s["reservations"].values()), Decimal(0)
            )
            if total + amount > Decimal(s["config"]["api_cap_usd"]):
                raise Pause("API cap: insufficient unreserved budget")
            s["reservations"][request_id] = {"usd": str(amount), "at": time.time()}
            s["last_operation_at"] = time.time()

    def reconcile(self, request_id, amount, usage):
        amount = Decimal(str(amount))
        if not amount.is_finite() or amount < 0:
            raise Pause("Invalid reconciled charge")
        exceeded = False
        with self.transaction() as s:
            reserved = Decimal(s["reservations"][request_id]["usd"])
            s["spent_usd"] = str(Decimal(s["spent_usd"]) + amount)
            del s["reservations"][request_id]
            s["charges"].append({"id": request_id, "usd": str(amount), "usage": usage})
            s["last_operation_at"] = time.time()
            if amount > reserved:
                s["status"] = "paused_charge_exceeded_reservation"
                exceeded = True
        if exceeded:
            raise Pause("Provider charge exceeded reservation; campaign paused")


def baseline(method, raw):
    if raw is None:
        return {"outcome": "missing", "seconds": None, "raw": raw}
    value = raw.get("time") if isinstance(raw, dict) else raw
    error = raw.get("error") if isinstance(raw, dict) else None
    code = str(error or value or "").lower()
    if "timeout" in code:
        outcome, seconds = "timeout", None
    elif code in ("cex", "falsified", "result_false", "false"):
        outcome, seconds = "counterexample", None
    elif error:
        outcome, seconds = "error", None
    else:
        try:
            if (
                method == "vcf"
                and isinstance(value, str)
                and re.fullmatch(r"\d+:\d{2}:\d{2}(?:\.\d+)?", value)
            ):
                hours, minutes, seconds_part = value.split(":")
                seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds_part)
            else:
                seconds = float(value)
            if not math.isfinite(seconds) or seconds < 0:
                raise ValueError()
            outcome = "proved"
        except (ValueError, TypeError):
            outcome, seconds = ("missing" if value is None else "error"), None
    return {"outcome": outcome, "seconds": seconds, "raw": raw}


def without_comments(text):
    # Keep character offsets so insertion never changes original bytes.
    return re.sub(
        r"//[^\n]*|/\*.*?\*/",
        lambda m: "".join("\n" if c == "\n" else " " for c in m[0]),
        text,
        flags=re.DOTALL,
    )


def task_context(path):
    text = path.read_text()
    code = without_comments(text)
    props = list(
        re.finditer(
            r"\bproperty\s+prop\s*;(?P<body>.*?)\bendproperty\b", code, re.DOTALL
        )
    )
    if len(props) != 1:
        raise Pause(f"{path.name}: expected one prop declaration")
    p = props[0]
    modules = list(re.finditer(r"\bmodule\s+(\w+)\b", code[: p.start()]))
    top = modules[-1][1]
    insert = code.index("endmodule", p.end())
    if re.search(r"\b(assert|assume)\b|`include|`define", code):
        raise Pause(
            f"{path.name}: unsupported pre-existing directive requires explicit inventory"
        )
    rst = bool(re.search(r"\binput(?:\s+(?:reg|logic|wire))?\s+rst\b", code))
    key = path.name.removesuffix(".sv").removesuffix("_ebmc")
    return {
        "id": key,
        "source": str(path.resolve()),
        "source_sha256": digest(path),
        "top": top,
        "target": text[p.start() : p.end()],
        "target_body": text[p.start("body") : p.end("body")],
        "insert_offset": insert,
        "reset": "rst" if rst else None,
        "premises": [
            {
                "id": "published_reset",
                "kind": "supplied",
                "statement": f"EBMC --reset {top}.rst",
                "source": "pinned src/evaluation.py reset policy, qualified for EBMC 6.0",
                "scope": top,
            }
        ]
        if rst
        else [],
        "clocks": re.findall(r"@\s*\([^)]*\)", code),
        "reset_behavior": {
            "signal": "rst" if rst else None,
            "property_disable_iff": re.findall(r"disable\s+iff\s*\([^)]*\)", code),
        },
        "initialization": {
            "initial_blocks": re.findall(
                r"\binitial\b\s*(?:begin.*?\bend\b|[^;]*;)", code, re.DOTALL
            ),
            "declaration_initializers": [
                line.strip()
                for line in code.splitlines()
                if re.search(r"\b(?:logic|reg|wire|integer|bit)\b[^;]*=", line)
            ],
        },
        "parameters": {
            "declarations": re.findall(r"\bparameter\b[^;,)]+", code),
            "overrides": [],
        },
        "semantic_checks": {
            "reset": "published harness flag; backend semantics validated in smoke tests",
            "vacuity": "unresolved: no complete antecedent reachability audit",
            "premise_consistency": "unresolved: no complete reachability audit",
        },
    }


def inventory():
    paths = sorted(BENCH.glob("*.sv"))
    if len(paths) != 31:
        raise Pause(f"Expected 31 tasks, found {len(paths)}")
    tables = {
        m: read_json(BENCH / "sota_timings" / f"{m}.json")
        for m in ("ric3", "jasper", "vcf")
    }
    groups = read_json(BENCH / "bookkeeping.json")
    tasks = []
    for p in paths:
        task = task_context(p)
        if task["id"] not in groups:
            raise Pause("Unmatched benchmark identifier: " + task["id"])
        task["baselines"] = {
            m: baseline(m, t.get(task["id"])) for m, t in tables.items()
        }
        tasks.append(task)
    if len({t["id"] for t in tasks}) != 31:
        raise Pause("Duplicate task identifier")
    return tasks


def parse_result(report, expected, mode, run):
    """Only exact property statuses in EBMC 6.0's JSON report carry authority."""
    if run.get("status") == "timeout":
        return {"outcome": "timeout"}
    if (
        run.get("status") != "completed"
        or not run.get("inputs_unchanged")
        or run.get("errors")
    ):
        return {"outcome": "setup_error"}
    if run.get("exit_code") not in (0, 10):
        return {"outcome": "setup_error"}
    if not isinstance(report, dict) or not isinstance(report.get("properties"), list):
        return {"outcome": "setup_error"}
    matches = [p for p in report["properties"] if p.get("identifier") == expected]
    if len(matches) != 1:
        return {
            "outcome": "setup_error",
            "reason": "missing or duplicate exact property identifier",
        }
    p = matches[0]
    status = p.get("status", "")
    if status == "PROVED":
        outcome = (
            "proved"
            if mode in ("k-induction", "ic3", "bdd") and p.get("proof_via")
            else "bounded"
        )
    elif status.startswith("PROVED up to bound "):
        outcome = "bounded"
    elif status == "REFUTED" or status.startswith("REFUTED up to bound "):
        outcome = "counterexample" if p.get("trace") else "unknown"
    elif status.startswith("INCONCLUSIVE"):
        outcome = "induction_failure" if mode == "k-induction" else "unknown"
    elif status.startswith(("FAILURE", "UNSUPPORTED")):
        outcome = "setup_error"
    else:
        outcome = "unknown"
    return {"outcome": outcome, "property": p}


def validate_expression(expr):
    if not isinstance(expr, str) or not expr.strip() or len(expr) > 16000:
        raise ValueError(
            "Expected a nonempty property body of at most 16000 characters"
        )
    if re.search(r'[;`\\"#]|//|/\*|\*/|\+\+|--|(?<![<>=!])=(?!=)', expr):
        raise ValueError(
            "Helper must be a declarative property expression, without directives or assignments"
        )
    if re.search(
        r"\b(assert|assume|cover|property|endproperty|module|endmodule|begin|end|initial|always|function|task|force|release|assign|prop|sva_[A-Za-z0-9_]+)\b",
        expr,
    ):
        raise ValueError("Forbidden helper token or target reference")
    calls = re.findall(r"([A-Za-z_$][\w$]*)\s*\(", expr)
    if any(
        c
        not in (
            "iff",
            "$past",
            "$stable",
            "$rose",
            "$fell",
            "$isunknown",
            "$onehot",
            "$onehot0",
            "$countones",
            "$unsigned",
            "$signed",
        )
        for c in calls
    ):
        raise ValueError("Only whitelisted pure SVA functions are supported")


def closure(candidates, target):
    done, visiting, order = set(), set(), []

    def visit(cid):
        if cid in visiting:
            raise ValueError("Dependency cycle")
        if cid in done:
            return
        c = candidates[cid]
        if c.get("retracted"):
            raise ValueError("Retracted dependency")
        visiting.add(cid)
        for dep in c["dependencies"]:
            if candidates[dep]["includes_target"]:
                raise ValueError("Target cannot justify a helper or another target")
            visit(dep)
        visiting.remove(cid)
        done.add(cid)
        order.append(cid)

    visit(target)
    return order
