"""Near-N log N variant of the free-variable proof DAG for lrg_arb_lrg_N.

In gen_free.py two lemmas cost super-linear engine time because each needs global reasoning
through a symbolic-index mux: D (rank distinctness, an N-state induction) and M (the min chain,
an N-step transitivity). Here both are made local:

D: shadows sh_i/sh_j equal free_i/free_j in the first cycle after reset (no-reset registers are X
   during Jasper's reset, so they are selected by a `started` flag rather than reset-loaded) and apply the RTL's per-index rank update
   (rank_upd) with the same chosen_priority. S links ranks[free_i] == sh_i (a local induction
   step), DS is distinctness of the 2-register shadow system, D follows combinationally.

M: min_chain (same comparator chain as the RTL) is instantiated on the real ranks/requests (rpm)
   and on symbolic frozen snapshots (spm). EQ: rpm[N] == chosen_priority. A walker (wk, wacc)
   folds the snapshot chain one position per cycle, turning the N-step transitivity into the
   1-step inductive invariant WI. MS: at wk == N the snapshot min is <= every requesting rank.
   Since snap_r/snap_q/free_j are arbitrary constants and wk deterministically reaches N, MS
   gives PHI(v, y): y<N && v.q[y] |-> chain(v)[N] <= v.r[y] for every valuation v; it is assumed
   at v = (ranks, in_req_vec), y = free_j (the same free-variable instantiation rule as before,
   plus dropping the wk == N premise).

Obligations and assumptions:
  C                                   --                          (cp cut)
  S   ranks[i]==sh_i, ranks[j]==sh_j  --                          (cp cut)
  DS  sh_i != sh_j, both < N          --                          (cp cut)
  D   ranks[i] != ranks[j]            -- S, DS                    (cp cut)
  G   grant[i] |-> ranks[i]==cp       --                          (ranks cut)
  EQ  rpm[N] == cp                    --                          (ranks cut)
  WI  walker invariant                --
  MS  wk==N |-> PHI(snap, j)          -- WI
  M   req[j] |-> cp <= ranks[j]       -- EQ, PHI(real, j)         (ranks cut)
  target                              -- G(a), M(b), D(a,b), C    (cp cut)
"""

import pathlib
import sys

from gen import A, B, CONTROL_ENGINES, TARGET
from gen_free import FI, FJ, Instance, Level, Obligation, chosen_ok, distinct, free_harness_text, grant, minimal, \
    tcl_text

HERE: pathlib.Path = pathlib.Path(__file__).parent
ENGINES: str = "Hp"
RANKS_CUT: tuple[str, ...] = ("ranks",)

AUX_DECLS: str = """\
function automatic logic [NUM_REQ_W-1:0] rank_upd(input logic [NUM_REQ_W-1:0] r, input logic [NUM_REQ_W-1:0] c);
        return (r == c) ? NUM_REQ_W'(NUM_REQ-1) : (r > c) ? NUM_REQ_W'(r - 1) : r;
endfunction
logic started;
always @(posedge clk or posedge rst) started <= rst ? 1'b0 : 1'b1;
logic [NUM_REQ_W-1:0] sh_i_q, sh_j_q, sh_i, sh_j;
assign sh_i = started ? sh_i_q : free_i;
assign sh_j = started ? sh_j_q : free_j;
always @(posedge clk) begin sh_i_q <= rank_upd(sh_i, chosen_priority); sh_j_q <= rank_upd(sh_j, chosen_priority); end
logic [NUM_REQ_W-1:0] rpm [NUM_REQ:0];
min_chain #(.N(NUM_REQ), .W(NUM_REQ_W)) chain_real (.r(ranks), .q(in_req_vec), .pm(rpm));
logic [NUM_REQ_W-1:0] snap_r [NUM_REQ-1:0];
logic [NUM_REQ-1:0] snap_q;
always @(posedge clk) begin snap_r <= snap_r; snap_q <= snap_q; end
logic [NUM_REQ_W-1:0] spm [NUM_REQ:0];
min_chain #(.N(NUM_REQ), .W(NUM_REQ_W)) chain_snap (.r(snap_r), .q(snap_q), .pm(spm));
logic [NUM_REQ_W-1:0] wk, wacc;
always @(posedge clk or posedge rst)
        if (rst) begin wk <= '0; wacc <= NUM_REQ_W'(NUM_REQ); end
        else if (wk < NUM_REQ) begin
                wacc <= (snap_q[wk] && snap_r[wk] < wacc) ? snap_r[wk] : wacc;
                wk <= wk + 1'b1;
        end
"""

MIN_CHAIN: str = """
module min_chain #(parameter int N = 2, parameter int W = 2)
        (input logic [W-1:0] r [N-1:0], input logic [N-1:0] q, output logic [W-1:0] pm [N:0]);
        assign pm[0] = W'(N);
        for (genvar k = 0; k < N; k++) begin : step
                assign pm[k+1] = (q[k] && r[k] < pm[k]) ? r[k] : pm[k];
        end
endmodule
"""


def nlogn_harness_text(n: int) -> str:
    src: str = free_harness_text(n)
    cut: int = src.rindex(f"{TARGET}: assert")
    return src[:cut] + AUX_DECLS + src[cut:] + MIN_CHAIN


def link(n: int, x: str, sh: str) -> str:
    return f"{x} < {n} |-> ranks[{x}] == {sh}"


def shadow_distinct(n: int) -> str:
    return f"{FI} < {n} && {FJ} < {n} && {FI} != {FJ} |-> sh_i != sh_j && sh_i < {n} && sh_j < {n}"


def walker_inv(n: int) -> str:
    return (f"wk <= {n} && wacc == spm[wk] && "
            f"(!({FJ} < wk && snap_q[{FJ}]) || wacc <= snap_r[{FJ}])")


def snap_min(n: int, op: str = "<=") -> str:
    return f"wk == {n} && {FJ} < {n} && snap_q[{FJ}] |-> spm[{n}] {op} snap_r[{FJ}]"


def real_min(n: int) -> str:
    return f"{FJ} < {n} && in_req_vec[{FJ}] |-> rpm[{n}] <= ranks[{FJ}]"


def equiv(n: int) -> str:
    return f"rpm[{n}] == chosen_priority"


def obligations(n: int) -> dict[str, Obligation]:
    target_deps: tuple[Instance, ...] = (
        Instance("G_at_a", "G", grant(n, A)),
        Instance("M_at_b", "M", minimal(n, B)),
        Instance("D_at_ab", "D", distinct(n, A, B)),
        Instance("C_inst", "C", chosen_ok(n)),
    )
    obs: tuple[Obligation, ...] = (
        Obligation("C", chosen_ok(n), ()),
        Obligation("S_i", link(n, FI, "sh_i"), ()),
        Obligation("S_j", link(n, FJ, "sh_j"), ()),
        Obligation("DS", shadow_distinct(n), ()),
        Obligation("D", distinct(n, FI, FJ),
                   (Instance("S_i_inst", "S_i", link(n, FI, "sh_i")),
                    Instance("S_j_inst", "S_j", link(n, FJ, "sh_j")),
                    Instance("DS_inst", "DS", shadow_distinct(n)))),
        Obligation("G", grant(n, FI), ()),
        Obligation("EQ", equiv(n), ()),
        Obligation("WI", walker_inv(n), ()),
        Obligation("MS", snap_min(n), (Instance("WI_inst", "WI", walker_inv(n)),)),
        Obligation("M", minimal(n, FJ),
                   (Instance("EQ_inst", "EQ", equiv(n)), Instance("PHI_real", "MS", real_min(n)))),
        Obligation(TARGET, "prop", target_deps),
    )
    return {o.name: o for o in obs}


def dag_levels(n: int) -> list[Level]:
    ob: dict[str, Obligation] = obligations(n)
    witness: dict[str, str] = {"W_grant_req": f"chosen && o_grant_vec_ref[{A}] && in_req_vec[{B}]"}

    def lvl(name: str, keys: tuple[str, ...], cut_cp: bool, cuts: tuple[str, ...] = ()) -> Level:
        return Level(name, tuple(ob[k] for k in keys), cut_cp, {}, False, ENGINES, cuts)

    return [lvl("P_C", ("C",), True),
            lvl("P_Si", ("S_i",), True),
            lvl("P_Sj", ("S_j",), True),
            lvl("P_DS", ("DS",), True),
            lvl("P_D", ("D",), True),
            lvl("P_G", ("G",), False, RANKS_CUT),
            lvl("P_EQ", ("EQ",), False, RANKS_CUT),
            lvl("P_WI", ("WI",), False),
            lvl("P_MS", ("MS",), False),
            lvl("P_M", ("M",), False, RANKS_CUT),
            Level("P_T", (ob[TARGET],), True, witness, True, ENGINES)]


def control_levels(n: int) -> list[Level]:
    """Expected cex: free_i ranges over all indices; M is necessary; MS is tight; the walker finishes (cover)."""
    ob: dict[str, Obligation] = obligations(n)
    tight: Obligation = Obligation("X1_R", f"{FI} < {n} |-> ranks[{FI}] < {n - 1}", ())
    no_min: Obligation = Obligation("X3_target", "prop", tuple(d for d in ob[TARGET].deps if d.lemma != "M"))
    strict: Obligation = Obligation("X4_MS", snap_min(n, "<"), ob["MS"].deps)
    return [Level("X1", (tight,), True, {}, False, CONTROL_ENGINES),
            Level("X3", (no_min,), True, {}, True, CONTROL_ENGINES),
            Level("X4", (strict,), False, {"V_walk_done": f"wk == {n}"}, False, CONTROL_ENGINES)]


def link_at(k: int, x: str, sh: str) -> str:
    return f"{x} == {k} |-> ranks[{k}] == {sh}"


def explore_levels(n: int) -> list[Level]:
    """Engine variants of P_S; per-index split of S (N local inductions) and D from the split."""
    ob: dict[str, Obligation] = obligations(n)
    split_i: tuple[Obligation, ...] = tuple(Obligation(f"S_i_{k}", link_at(k, FI, "sh_i"), ()) for k in range(n))
    split_d: Obligation = Obligation(
        "D", ob["D"].expr,
        tuple(Instance(f"S_{x}_{k}_inst", "S_k", link_at(k, f, f"sh_{x}"))
              for x, f in (("i", FI), ("j", FJ)) for k in range(n))
        + (Instance("DS_inst", "DS", shadow_distinct(n)),))
    return ([Level(f"ES1_{e}", (ob["S_i"],), True, {}, False, e) for e in ("Hp", "Mp", "N", "I", "AM")]
            + [Level(f"ES2_{e}", (ob["S_i"], ob["S_j"]), True, {}, False, e) for e in ("Mp", "N", "I")]
            + [Level(f"ESK_{e}", split_i, True, {}, False, e) for e in ("Hp",)]
            + [Level("ED_split", (split_d,), True, {}, False, ENGINES)])


def main(argv: list[str]) -> None:
    n: int = int(argv[1])
    out: pathlib.Path = HERE / "work" / "nlogn" / f"N{n}"
    for level in dag_levels(n) + control_levels(n) + explore_levels(n):
        d: pathlib.Path = out / level.name
        d.mkdir(parents=True, exist_ok=True)
        (d / "harness.sv").write_text(nlogn_harness_text(n))
        (d / "run.tcl").write_text(tcl_text(n, level))
    (out / "dag_levels.txt").write_text(" ".join(lvl.name for lvl in dag_levels(n)) + "\n")


if __name__ == "__main__":
    main(sys.argv)
