"""Free-variable variant of the proof DAG for lrg_arb_lrg_N: O(1) obligations instead of O(N^2).

The harness gets two symbolic constants free_i, free_j: registers without reset that hold their
(arbitrary) initial value forever. A lemma proven over free_i/free_j holds for every index value,
so it may be assumed at any index expression (here the target's own a, b).

Lemmas, parameterised by index expressions x, y:
  R(x)    x<N |-> ranks[x] < N                                    (cut)
  C       chosen |-> a<N && b<N && a!=b                           (cut)
  D(x,y)  x<N && y<N && x!=y |-> ranks[x] != ranks[y]             (cut)
  G(x)    x<N && o_grant_vec_ref[x] |-> ranks[x] == cp            (concrete)
  M(y)    y<N && in_req_vec[y] |-> cp <= ranks[y]                 (concrete)

Obligations (proven at i = free_i, j = free_j):
  R  = R(i)     --
  C             --
  D  = D(i,j)   -- R(i), R(j)
  G  = G(i)     --
  M  = M(j)     --
  target prop   -- G(a), M(b), D(a,b), C
(a = arbitrary_requester, b = another_arbitrary_requester, cp = chosen_priority.)
"""

import pathlib
import sys
from dataclasses import dataclass

from gen import A, B, CONTROL_ENGINES, CP, DAG_ENGINES, TARGET, TIME_LIMIT, harness_text

HERE: pathlib.Path = pathlib.Path(__file__).parent
FI: str = "free_i"
FJ: str = "free_j"


@dataclass(frozen=True)
class Instance:
    """A proven lemma assumed at specific index expressions."""
    name: str
    lemma: str
    expr: str


@dataclass(frozen=True)
class Obligation:
    name: str
    expr: str
    deps: tuple[Instance, ...]


@dataclass(frozen=True)
class Level:
    name: str
    asserts: tuple[Obligation, ...]
    cut_cp: bool
    covers: dict[str, str]
    prove_target: bool
    engines: str = DAG_ENGINES


def rng(n: int, x: str) -> str:
    return f"{x} < {n} |-> ranks[{x}] < {n}"


def distinct(n: int, x: str, y: str) -> str:
    return f"{x} < {n} && {y} < {n} && {x} != {y} |-> ranks[{x}] != ranks[{y}]"


def grant(n: int, x: str) -> str:
    return f"{x} < {n} && o_grant_vec_ref[{x}] |-> ranks[{x}] == {CP}"


def minimal(n: int, y: str) -> str:
    return f"{y} < {n} && in_req_vec[{y}] |-> {CP} <= ranks[{y}]"


def chosen_ok(n: int) -> str:
    return f"chosen |-> ({A} < {n} && {B} < {n} && {A} != {B})"


def free_harness_text(n: int) -> str:
    src: str = harness_text(n)
    cut: int = src.rindex(f"{TARGET}: assert")
    free: str = (f"logic [NUM_REQ_W-1:0] {FI}, {FJ};\n"
                 f"always @(posedge clk) begin {FI} <= {FI}; {FJ} <= {FJ}; end\n")
    return src[:cut] + free + src[cut:]


def obligations(n: int) -> tuple[Obligation, ...]:
    target_deps: tuple[Instance, ...] = (
        Instance("G_at_a", "G", grant(n, A)),
        Instance("M_at_b", "M", minimal(n, B)),
        Instance("D_at_ab", "D", distinct(n, A, B)),
        Instance("C_inst", "C", chosen_ok(n)),
    )
    return (
        Obligation("R", rng(n, FI), ()),
        Obligation("C", chosen_ok(n), ()),
        Obligation("D", distinct(n, FI, FJ),
                   (Instance("R_at_i", "R", rng(n, FI)), Instance("R_at_j", "R", rng(n, FJ)))),
        Obligation("G", grant(n, FI), ()),
        Obligation("M", minimal(n, FJ), ()),
        Obligation(TARGET, "prop", target_deps),
    )


def dag_levels(n: int) -> list[Level]:
    ob: dict[str, Obligation] = {o.name: o for o in obligations(n)}
    witness: dict[str, str] = {"W_grant_req": f"chosen && o_grant_vec_ref[{A}] && in_req_vec[{B}]"}
    return [Level("F1", (ob["R"], ob["C"]), True, {}, False),
            Level("F2", (ob["D"],), True, {}, False),
            Level("F3", (ob["G"], ob["M"]), False, {}, False),
            Level("F4", (ob[TARGET],), True, witness, True)]


def control_levels(n: int) -> list[Level]:
    """Negative controls, all expected cex: free_i must range over every index; M (lost by the cut) is necessary."""
    tight: Obligation = Obligation("X1_R", f"{FI} < {n} |-> ranks[{FI}] < {n - 1}", ())
    target: Obligation = obligations(n)[-1]
    no_min: Obligation = Obligation(
        "X3_target", "prop", tuple(d for d in target.deps if d.lemma != "M"))
    return [Level("X1", (tight,), True, {}, False, CONTROL_ENGINES),
            Level("X3", (no_min,), True, {}, True, CONTROL_ENGINES)]


def tcl_text(n: int, level: Level) -> str:
    assumed: dict[str, str] = {d.name: d.expr for ob in level.asserts for d in ob.deps}
    own: tuple[Obligation, ...] = tuple(o for o in level.asserts if o.expr != "prop")
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
    lines += [f"assume -name {k} {{{v}}}" for k, v in sorted(assumed.items())]
    lines += [f"assert -name {o.name} {{{o.expr}}}" for o in own]
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
    out: pathlib.Path = HERE / "work" / "free" / f"N{n}"
    for level in dag_levels(n) + control_levels(n):
        d: pathlib.Path = out / level.name
        d.mkdir(parents=True, exist_ok=True)
        (d / "harness.sv").write_text(free_harness_text(n))
        (d / "run.tcl").write_text(tcl_text(n, level))
    (out / "dag_levels.txt").write_text(" ".join(lvl.name for lvl in dag_levels(n)) + "\n")


if __name__ == "__main__":
    main(sys.argv)
