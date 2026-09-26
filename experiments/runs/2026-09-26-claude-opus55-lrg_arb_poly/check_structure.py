"""Syntactic side conditions of the proof that EBMC cannot discharge.

Usage:
  python3 check_structure.py rewrite N_DIR       the M -> M' rewrite is covered by step1.sv and step2.sv
  python3 check_structure.py conservative N_DIR  every harness is M' (or M) plus a conservative extension

N_DIR is a generated directory such as proof/N16. Prints a JSON report; exits 0 iff every check passes.

rewrite checks
  - the benchmark always_comb block is ORIGINAL_SKELETON with two loop bodies B1, B2 filled in, and
    M' replaces exactly that block by REWRITTEN_SKELETON with bodies C1, C2
  - B1, B2, C1, C2 only mention the block state, ranks, in_req_vec, idx, NUM_REQ and if/else/begin/end,
    and never write idx (so each body is one straight-line iteration of its loop at a fixed idx)
  - the block state declarations in step1.sv/step2.sv are the benchmark declarations, suffixed
  - step1.sv and step2.sv are exactly the step miters of (B1, C1) and (B2, C2)
conservative checks
  - each harness file is the model followed by a snippet inserted just before `endmodule`
  - every name the snippet declares is fresh w.r.t. the model, and every name it assigns is its own
  - the snippet contains no construct that could constrain or drive the model other than `assume property`
  - a lemma chunk with a given header is identical in every harness (proved and assumed text agree)
  - every assumed property is asserted by some DAG harness, and the assume graph is acyclic
"""

import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import make_proof as mp

IDENTIFIER: re.Pattern[str] = re.compile(r"\b[A-Za-z_]\w*\b")
LITERAL: re.Pattern[str] = re.compile(r"\d*'[bdhoBDHO]?[0-9a-fA-FxXzZ_]+")
IDX_WRITE: re.Pattern[str] = re.compile(r"\bidx\s*(?:=(?!=)|\+\+|--|[-+*/]=)|(?:\+\+|--)\s*idx\b")
BODY_VOCABULARY: frozenset[str] = frozenset(
    mp.BLOCK_STATE + ("ranks", "in_req_vec", "idx", "NUM_REQ", "if", "else", "begin", "end")
)
SNIPPET_DECLARATION: re.Pattern[str] = re.compile(
    r"\b(?:logic|wire|reg)\b(?:\s*\[[^\]]*\])?\s+(\w+)|\bproperty\s+(\w+)|\bgenvar\s+(\w+)|\bbegin\s*:\s*(\w+)"
)
SNIPPET_ASSIGN: re.Pattern[str] = re.compile(r"\bassign\s+(\w+)|^\s*(\w+)(?:\[[^\]]*\])?\s*<?=(?!=)", re.MULTILINE)
SNIPPET_FORBIDDEN: re.Pattern[str] = re.compile(
    r"\b(?:always_comb|always_ff|always_latch|initial|force|release|deassign|restrict|bind|defparam)\b|\$\w+"
)
ASSUMED: re.Pattern[str] = re.compile(r"^assume property \((\w+)\);$", re.MULTILINE)
ASSERTED: re.Pattern[str] = re.compile(r"^assert property \((\w+)\);$", re.MULTILINE)
CHUNK_HEADER: re.Pattern[str] = re.compile(r"^// [^\n]*$", re.MULTILINE)
LINE_COMMENT: re.Pattern[str] = re.compile(r"//[^\n]*")
SIZE_DIR: re.Pattern[str] = re.compile(r"N(\d+)")


class Report(NamedTuple):
    failures: list[str]
    details: dict[str, object]


def size_of(n_dir: Path) -> int:
    match: re.Match[str] | None = SIZE_DIR.fullmatch(n_dir.name)
    if match is None:
        raise ValueError(f"{n_dir} is not named N<size>")
    return int(match.group(1))


def failure_if(condition: object, message: str) -> list[str]:
    return [message] if condition else []


def identifiers(code: str) -> set[str]:
    return set(IDENTIFIER.findall(LITERAL.sub(" ", code)))


def body_failures(label: str, body: str) -> list[str]:
    foreign: set[str] = identifiers(body) - BODY_VOCABULARY
    return failure_if(foreign, f"{label} mentions {sorted(foreign)}") + failure_if(
        IDX_WRITE.search(body), f"{label} writes idx"
    )


def declaration_line(text: str, name: str) -> str | None:
    match: re.Match[str] | None = re.search(rf"^logic\b[^;\n]*\b{name}\b[^;\n]*;[ \t]*$", text, re.MULTILINE)
    return match.group(0).strip() if match else None


def declaration_failures(source: str, step_name: str, step_text: str, names: tuple[str, ...]) -> list[str]:
    expected: dict[str, str | None] = {
        name + suffix: (lambda line: None if line is None else mp.with_suffix(line, suffix))(
            declaration_line(source, name)
        )
        for name in names
        for suffix in ("_o", "_n")
    }
    return [
        f"{step_name}: declaration of {renamed} differs from the benchmark"
        for renamed, line in expected.items()
        if (actual := declaration_line(step_text, renamed)) is not None and actual != line
    ] + [
        f"{step_name}: {renamed} undeclared"
        for renamed in expected
        if renamed in identifiers(step_text) and declaration_line(step_text, renamed) is None
    ]


def check_rewrite(n_dir: Path) -> Report:
    n: int = size_of(n_dir)
    source: str = mp.BENCHMARK.read_text()
    block: str = mp.original_block(source)
    original: mp.LoopBodies = mp.loop_bodies(block)
    rewritten_model: str = mp.rewritten_model(source, n)
    expected_steps: dict[str, str] = mp.step_harnesses(original, mp.REWRITTEN_BODIES, n)
    bodies: dict[str, str] = {
        "B1": original.min_step,
        "B2": original.update_step,
        "C1": mp.REWRITTEN_BODIES.min_step,
        "C2": mp.REWRITTEN_BODIES.update_step,
    }
    failures: list[str] = (
        [f for label, body in bodies.items() for f in body_failures(label, body)]
        + failure_if(
            mp.fill(mp.ORIGINAL_SKELETON, original) != block, "benchmark block != ORIGINAL_SKELETON(B1, B2)"
        )
        + failure_if(
            mp.original_block(rewritten_model) != mp.fill(mp.REWRITTEN_SKELETON, mp.REWRITTEN_BODIES),
            "M' block != REWRITTEN_SKELETON(C1, C2)",
        )
        + failure_if(
            mp.with_block(rewritten_model, block) != mp.with_size(source, n),
            "M' differs from M outside the always_comb block",
        )
        + [
            f"{name} differs from the generated step miter"
            for name, text in expected_steps.items()
            if (n_dir / name).read_text() != text
        ]
        + [
            f
            for name, text in expected_steps.items()
            for f in declaration_failures(source, name, (n_dir / name).read_text(), mp.BLOCK_STATE)
        ]
    )
    return Report(failures, {"n": n, "bodies": bodies, "step_files": sorted(expected_steps)})


class Split(NamedTuple):
    model: str
    snippet: str


def split_harness(text: str, model: str) -> Split | None:
    cut: int = model.index(mp.MODULE_END)
    prefix, suffix = model[:cut], model[cut:]
    fits: bool = text.startswith(prefix) and text.endswith(suffix) and len(text) >= len(model)
    return Split(model, text[len(prefix) : len(text) - len(suffix)]) if fits else None


def declared_names(snippet: str) -> set[str]:
    return {name for groups in SNIPPET_DECLARATION.findall(snippet) for name in groups if name}


def assigned_names(snippet: str) -> set[str]:
    return {name for groups in SNIPPET_ASSIGN.findall(snippet) for name in groups if name}


def lemma_chunks(snippet: str) -> dict[str, str]:
    lemmas: str = snippet.split(mp.DIRECTIVES_HEADER)[0]
    starts: list[int] = [m.start() for m in CHUNK_HEADER.finditer(lemmas)]
    return {
        lemmas[start:].split("\n", 1)[0]: lemmas[start:stop]
        for start, stop in zip(starts, starts[1:] + [len(lemmas)])
    }


def snippet_failures(name: str, split: Split) -> list[str]:
    code: str = LINE_COMMENT.sub("", split.snippet)
    model_names: set[str] = identifiers(split.model)
    declared: set[str] = declared_names(code)
    clashes: set[str] = declared & model_names
    foreign_writes: set[str] = assigned_names(code) - declared
    forbidden: list[str] = SNIPPET_FORBIDDEN.findall(code)
    assert_count: int = len(ASSERTED.findall(split.snippet))
    return (
        failure_if(clashes, f"{name}: snippet redeclares model names {sorted(clashes)}")
        + failure_if(foreign_writes, f"{name}: snippet assigns non-snippet names {sorted(foreign_writes)}")
        + failure_if(forbidden, f"{name}: snippet uses {sorted(set(forbidden))}")
        + failure_if(assert_count != 1, f"{name}: asserts {assert_count} properties")
    )


def cycle_failures(assumes: dict[str, set[str]]) -> list[str]:
    def reaches_itself(start: str) -> bool:
        seen: set[str] = set()
        frontier: set[str] = set(assumes.get(start, set()))
        while frontier:
            if start in frontier:
                return True
            seen |= frontier
            frontier = {nxt for node in frontier for nxt in assumes.get(node, set())} - seen
        return False

    return [f"assume cycle through {prop}" for prop in sorted(assumes) if reaches_itself(prop)]


def check_conservative(n_dir: Path) -> Report:
    n: int = size_of(n_dir)
    source: str = mp.BENCHMARK.read_text()
    rewritten_model: str = mp.rewritten_model(source, n)
    harness_files: list[str] = [f"{name}.sv" for name in mp.PROOF_DAG | mp.WITNESSES]
    models: dict[str, str] = {name: rewritten_model for name in harness_files} | {
        "original.sv": mp.with_size(source, n)
    }
    splits: dict[str, Split | None] = {
        name: split_harness((n_dir / name).read_text(), model) for name, model in models.items()
    }
    placement_failures: list[str] = [f"{name} is not model + snippet" for name, s in splits.items() if s is None]
    valid: dict[str, Split] = {name: s for name, s in splits.items() if s is not None}
    chunk_versions: dict[str, set[str]] = {}
    for split in valid.values():
        for header, chunk in lemma_chunks(split.snippet).items():
            chunk_versions.setdefault(header, set()).add(chunk.strip())
    directives: dict[str, dict[str, list[str]]] = {
        name: {"assumed": ASSUMED.findall(s.snippet), "asserted": ASSERTED.findall(s.snippet)}
        for name, s in valid.items()
    }
    dag_files: list[str] = [f"{name}.sv" for name in mp.PROOF_DAG]
    proved: set[str] = {p for name in dag_files if name in directives for p in directives[name]["asserted"]}
    assumes: dict[str, set[str]] = {
        p: set(directives[name]["assumed"]) for name in dag_files if name in directives for p in directives[name]["asserted"]
    }
    failures: list[str] = (
        placement_failures
        + [f for name, s in valid.items() for f in snippet_failures(name, s)]
        + [f"lemma chunk '{header}' differs between harnesses" for header, v in chunk_versions.items() if len(v) > 1]
        + [
            f"{name} assumes unproved {p}"
            for name, d in directives.items()
            for p in d["assumed"]
            if p not in proved
        ]
        + cycle_failures(assumes)
    )
    return Report(failures, {"n": n, "directives": directives, "lemma_chunks": sorted(chunk_versions)})


CHECKS: dict[str, Callable[[Path], Report]] = {"rewrite": check_rewrite, "conservative": check_conservative}


def main(check: str, n_dir: Path) -> int:
    report: Report = CHECKS[check](n_dir)
    print(json.dumps({"check": check, "dir": str(n_dir), "ok": not report.failures, **report._asdict()}, indent=2))
    return 0 if not report.failures else 1


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in CHECKS:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], Path(sys.argv[2])))
