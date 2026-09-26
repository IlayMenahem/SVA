"""Generate the Jasper proof DAG for lrg_arb_lrg_N.

cp = chosen_priority (combinational min over requesting ranks). Levels marked "cut" run with
`stopat cp`, an over-approximation (cp becomes a free input), so proofs there hold concretely.

Obligations (id: statement -- dependencies):
  R_i    ranks[i] < N                                        -- none              (L1, cut)
  C      chosen |-> a<N && b<N && a!=b                       -- none              (L1, cut)
  D_i_j  ranks[i] != ranks[j], i<j                           -- R_i, R_j          (L2, cut)
  G_i    o_grant_vec_ref[i] |-> ranks[i] == cp               -- none              (L3, concrete)
  M_j    in_req_vec[j] |-> cp <= ranks[j]                    -- none              (L3, concrete)
  Q_i_j  grant[i] && req[j] |-> ranks[i] < ranks[j], i!=j    -- G_i, M_j, D_ij    (L4, cut)
  A_j    chosen && grant[a] && req[j] && a!=j |-> ranks[a] < ranks[j]  -- Q_*_j  (L5, cut)
  target prop                                                -- A_*, C            (L6, cut)
(a = arbitrary_requester, b = another_arbitrary_requester.)

Every level (and shard) is an independent Jasper invocation, so all may run in parallel.
"""

import functools
import itertools
import pathlib
import sys
from dataclasses import dataclass

HERE: pathlib.Path = pathlib.Path(__file__).parent
BENCH: pathlib.Path = HERE / "../../../datasets/raw/large-lemma-miners/benchmarks/hard"
CP: str = "chosen_priority"
A: str = "arbitrary_requester"
B: str = "another_arbitrary_requester"
TARGET: str = "target"
SHARD_WEIGHT: int = 1024
TIME_LIMIT: str = "1800s"
# Engines that closed every DAG lemma in auto mode; controls need bug hunters; "" keeps Jasper's auto set.
DAG_ENGINES: str = "Hp Mp N"
CONTROL_ENGINES: str = "Hp B Ht"


@dataclass(frozen=True)
class Obligation:
    expr: str
    deps: tuple[str, ...]


@dataclass(frozen=True)
class Level:
    name: str
    asserts: dict[str, Obligation]
    cut_cp: bool
    covers: dict[str, str]
    prove_target: bool
    engines: str = DAG_ENGINES


def harness_text(n: int) -> str:
    src: str = (BENCH / "lrg_arb_lrg_16_ebmc.sv").read_text()
    src = src.replace("parameter  NUM_REQ   = 16,", f"parameter  NUM_REQ   = {n},")
    # Verific rejects a declaration after statements; hoisting it is semantics-preserving.
    src = src.replace("        int idx;\n", "", 1)
    src = src.replace("always_comb begin\n", "always_comb begin\n        int idx;\n", 1)
    cut: int = src.rindex("endmodule")
    return src[:cut] + f"{TARGET}: assert property (prop);\n" + src[cut:]


def pair(i: int, j: int) -> str:
    return f"D_{min(i, j)}_{max(i, j)}"


def invariant_obligations(n: int) -> tuple[dict[str, Obligation], dict[str, Obligation]]:
    rng: dict[str, Obligation] = {f"R_{i}": Obligation(f"ranks[{i}] < {n}", ()) for i in range(n)}
    chosen: dict[str, Obligation] = {"C": Obligation(
        f"chosen |-> ({A} < {n} && {B} < {n} && {A} != {B})", ())}
    distinct: dict[str, Obligation] = {
        pair(i, j): Obligation(f"ranks[{i}] != ranks[{j}]", (f"R_{i}", f"R_{j}"))
        for i, j in itertools.combinations(range(n), 2)}
    return rng | chosen, distinct


def contract_obligations(n: int) -> dict[str, Obligation]:
    grant: dict[str, Obligation] = {
        f"G_{i}": Obligation(f"o_grant_vec_ref[{i}] |-> ranks[{i}] == {CP}", ()) for i in range(n)}
    minimal: dict[str, Obligation] = {
        f"M_{j}": Obligation(f"in_req_vec[{j}] |-> {CP} <= ranks[{j}]", ()) for j in range(n)}
    return grant | minimal


def order_obligations(n: int) -> dict[str, Obligation]:
    return {f"Q_{i}_{j}": Obligation(
        f"o_grant_vec_ref[{i}] && in_req_vec[{j}] |-> ranks[{i}] < ranks[{j}]",
        (f"G_{i}", f"M_{j}", pair(i, j)))
        for i, j in itertools.permutations(range(n), 2)}


def lift_obligations(n: int) -> dict[str, Obligation]:
    return {f"A_{j}": Obligation(
        f"chosen && o_grant_vec_ref[{A}] && in_req_vec[{j}] && {A} != {j} |-> ranks[{A}] < ranks[{j}]",
        tuple(f"Q_{i}_{j}" for i in range(n) if i != j))
        for j in range(n)}


def all_obligations(n: int) -> dict[str, Obligation]:
    inv, distinct = invariant_obligations(n)
    target: dict[str, Obligation] = {TARGET: Obligation(
        "prop", tuple(f"A_{j}" for j in range(n)) + ("C",))}
    return (inv | distinct | contract_obligations(n) | order_obligations(n)
            | lift_obligations(n) | target)


def session_weight(chunk: dict[str, Obligation]) -> int:
    return len(chunk) + len({d for ob in chunk.values() for d in ob.deps})


def add_to_chunks(chunks: list[dict[str, Obligation]], item: tuple[str, Obligation]
                  ) -> list[dict[str, Obligation]]:
    """Greedy packing: open a new session once asserts + assumptions would exceed SHARD_WEIGHT."""
    name, ob = item
    grown: dict[str, Obligation] = chunks[-1] | {name: ob} if chunks else {}
    fits: bool = bool(chunks) and session_weight(grown) <= SHARD_WEIGHT
    return chunks[:-1] + [grown] if fits else chunks + [{name: ob}]


def shards(name: str, obligations: dict[str, Obligation], cut_cp: bool) -> list[Level]:
    chunks: list[dict[str, Obligation]] = functools.reduce(add_to_chunks, obligations.items(), [])
    return [Level(f"{name}_s{k}", chunk, cut_cp, {}, False) for k, chunk in enumerate(chunks)]


def dag_levels(n: int) -> list[Level]:
    inv, distinct = invariant_obligations(n)
    obligations: dict[str, Obligation] = all_obligations(n)
    witness: dict[str, str] = {"W_grant_req": f"chosen && o_grant_vec_ref[{A}] && in_req_vec[{B}]"}
    return ([Level("L1", inv, True, {}, False)]
            + shards("L2", distinct, True)
            + shards("L3", contract_obligations(n), False)
            + shards("L4", order_obligations(n), True)
            + shards("L5", lift_obligations(n), True)
            + [Level("L6", {TARGET: obligations[TARGET]}, True, witness, True)])


def control_levels(n: int) -> list[Level]:
    """Negative controls: every assert here is expected to FAIL (cex)."""
    tight_range: dict[str, Obligation] = {
        f"X1_R_{i}": Obligation(f"ranks[{i}] < {n - 1}", ()) for i in range(n)}
    q01: Obligation = order_obligations(n)["Q_0_1"]
    uncontracted: dict[str, Obligation] = {"X3_Q_0_1": Obligation(q01.expr, (pair(0, 1),))}
    return [Level("X1", tight_range, True, {}, False, CONTROL_ENGINES),
            Level("X3", uncontracted, True, {}, False, CONTROL_ENGINES)]


def baseline_level() -> Level:
    return Level("B", {}, False, {}, True, "")


def tcl_text(n: int, level: Level, obligations: dict[str, Obligation]) -> str:
    assumed: list[str] = sorted({d for ob in level.asserts.values() for d in ob.deps})
    own: dict[str, Obligation] = {k: v for k, v in level.asserts.items() if k != TARGET}
    lines: list[str] = [
        "clear -all",
        "analyze -sv12 harness.sv",
        f"elaborate -top main -parameter NUM_REQ {n}",
        "clock clk",
        "reset rst",
        f"set_prove_time_limit {TIME_LIMIT}",
    ]
    lines += [f"set_engine_mode {{{level.engines}}}"] if level.engines else []
    lines += [f"stopat {CP}"] if level.cut_cp else []
    lines += [f"assume -name {k} {{{obligations[k].expr}}}" for k in assumed]
    lines += [f"assert -name {k} {{{v.expr}}}" for k, v in own.items()]
    lines += [f"cover -name {k} {{{v}}}" for k, v in level.covers.items()]
    lines += [] if level.prove_target else [f"assert -disable {{main.{TARGET}}}"]
    lines += [
        "prove -all",
        "report -summary -force -result -file summary.txt",
        "foreach p [get_property_list -include {type {assert cover}}] "
        "{ puts \"RESULT $p [get_status $p]\" }",
        "exit",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> None:
    n: int = int(argv[1])
    obligations: dict[str, Obligation] = all_obligations(n) | {
        k: v for lvl in control_levels(n) for k, v in lvl.asserts.items()}
    out: pathlib.Path = HERE / "work" / f"N{n}"
    levels: list[Level] = dag_levels(n) + control_levels(n) + [baseline_level()]
    for level in levels:
        d: pathlib.Path = out / level.name
        d.mkdir(parents=True, exist_ok=True)
        (d / "harness.sv").write_text(harness_text(n))
        (d / "run.tcl").write_text(tcl_text(n, level, obligations))
    (out / "dag_levels.txt").write_text(" ".join(lvl.name for lvl in dag_levels(n)) + "\n")


if __name__ == "__main__":
    main(sys.argv)
