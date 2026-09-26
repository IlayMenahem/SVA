"""Generate the polynomial proof harnesses for lrg_arb_lrg_N from the original benchmark.

Usage: python3 make_proof.py OUT_DIR N...

For each N writes OUT_DIR/N{n}/ with
  original.sv   the original benchmark at size N plus `assert property (prop)` (baseline)
  <node>.sv     one file per PROOF_DAG node: the rewritten model M' plus a harness that defines
                helper lemmas, assumes the node's dependencies and asserts the node's property
  step1.sv      M = M', loop 1: one iteration of the original body keeps relation R1 with M'
  step2.sv      M = M', loop 2: one iteration of the original body advances relation R2 with M'
  miter.sv      full combinational miter of the original and rewritten blocks (small N only)
  reach.sv      nonvacuity witness: BMC must refute `antecedent_unreachable` under all DAG lemmas
and OUT_DIR/N{n}/controls/ with step miters against mutated rewritten bodies (must be refuted),
and OUT_DIR/N{n}/discovery/ with the harnesses of abandoned candidates.

M' is the benchmark with NUM_REQ set to N and its always_comb block replaced by a ternary form
of the same loops. Everything else is kept verbatim; harnesses are appended before endmodule.
"""

import re
import sys
from pathlib import Path
from typing import NamedTuple

BENCHMARK: Path = Path(
    "/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/"
    "datasets/raw/large-lemma-miners/benchmarks/hard/lrg_arb_lrg_16_ebmc.sv"
)
PARAM_LINE: str = "parameter  NUM_REQ   = 16,"
BLOCK_START: str = "always_comb begin"
BLOCK_END: str = "end\nlogic chosen;"
MODULE_END: str = "endmodule //fv_env"
LAST_PORT: str = "input  logic [NUM_REQ_W-1:0] another_arbitrary_requester_raw  \n);"
BLOCK_STATE: tuple[str, ...] = ("ranks_raw", "chosen_priority", "o_grant_vec_raw")

ORIGINAL_SKELETON: tuple[str, str, str] = (
    "always_comb begin\n"
    "        chosen_priority = NUM_REQ;\n"
    "        ranks_raw = ranks;\n"
    "        int idx;\n"
    "        for (idx=0; idx < NUM_REQ; idx++) begin\n",
    "        end\n"
    "        \n"
    "        o_grant_vec_raw = '0;\n"
    "        for (idx=0; idx < NUM_REQ; idx++) begin\n",
    "        end\n"
    "        \n"
    "end\n",
)
REWRITTEN_SKELETON: tuple[str, str, str] = (
    "always_comb begin\n"
    "        chosen_priority = NUM_REQ;\n"
    "        int idx;\n"
    "        for (idx=0; idx < NUM_REQ; idx++) begin\n",
    "        end\n"
    "        for (idx=0; idx < NUM_REQ; idx++) begin\n",
    "        end\n"
    "end\n",
)
MIN_STEP: str = (
    "                chosen_priority = (in_req_vec[idx] && ranks[idx] < chosen_priority) ? ranks[idx] : chosen_priority;\n"
)
UPDATE_STEP: str = """                o_grant_vec_raw[idx] = ranks[idx] == chosen_priority;
                ranks_raw[idx] = (ranks[idx] == chosen_priority) ? NUM_REQ-1
                               : (ranks[idx] > chosen_priority) ? ranks[idx] - 3'b1 : ranks[idx];
"""
CUT_STEP_BLOCK: str = (
    "always_comb begin\n        chosen_priority = chosen_priority_cut;\n        int idx;\n"
    "        for (idx=0; idx < NUM_REQ; idx++) begin\n" + UPDATE_STEP + "        end\nend\n"
)
CUT_PORT: str = (
    "input  logic [NUM_REQ_W-1:0] another_arbitrary_requester_raw  ,\n"
    "input  logic [NUM_REQ_W-1:0] chosen_priority_cut\n);"
)
DIRECTIVES_HEADER: str = "\n// Obligation: assumed dependencies and the asserted property\n"

L_PERM: str = """
// L_perm: ranks is a permutation of 0..NUM_REQ-1 (every rank in range, ranks pairwise distinct)
logic [NUM_REQ-1:0] rank_in_range;
logic [NUM_REQ*NUM_REQ-1:0] rank_pair_distinct;
for (genvar i = 0; i < NUM_REQ; i++) begin : g_perm_i
        assign rank_in_range[i] = ranks[i] < NUM_REQ;
        for (genvar j = 0; j < NUM_REQ; j++) begin : g_perm_j
                assign rank_pair_distinct[i*NUM_REQ+j] = (i >= j) || (ranks[i] != ranks[j]);
        end
end
wire ranks_are_permutation = (&rank_in_range) && (&rank_pair_distinct);
property ranks_permutation;
   @(posedge clk) disable iff (rst) ranks_are_permutation;
endproperty
"""
L_SEL: str = """
// L_sel: once chosen, the two requesters are distinct, in-range indices
property requesters_selected;
   @(posedge clk) disable iff (rst) chosen |-> (arbitrary_requester < NUM_REQ)
        && (another_arbitrary_requester < NUM_REQ) && (arbitrary_requester != another_arbitrary_requester);
endproperty
"""
L_INIT: str = """
// L_init: before the requesters are chosen, ranks still hold their reset values
logic [NUM_REQ-1:0] rank_is_reset_value;
for (genvar k = 0; k < NUM_REQ; k++) begin : g_init
        assign rank_is_reset_value[k] = ranks[k] == k;
end
property ranks_reset_until_chosen;
   @(posedge clk) disable iff (rst) !chosen |-> &rank_is_reset_value;
endproperty
"""
L_AB: str = """
// L_ab: once chosen, the ranks of the two requesters are in range and distinct
property chosen_ranks_distinct;
   @(posedge clk) disable iff (rst) chosen |-> (ranks[arbitrary_requester] < NUM_REQ)
        && (ranks[another_arbitrary_requester] < NUM_REQ)
        && (ranks[arbitrary_requester] != ranks[another_arbitrary_requester]);
endproperty
"""
GHOST: str = """
// Ghost state (write-only, never read by the design): the ranks of the two chosen requesters,
// tracked without indexing ranks. The next-requester logic mirrors the design's selection.
wire next_pair_invalid = (arbitrary_requester_raw == another_arbitrary_requester_raw)
        || arbitrary_requester_raw >= NUM_REQ || another_arbitrary_requester_raw >= NUM_REQ;
wire [NUM_REQ_W-1:0] next_requester_a = next_pair_invalid ? 3'b0 : arbitrary_requester_raw;
wire [NUM_REQ_W-1:0] next_requester_b = next_pair_invalid ? 3'b1 : another_arbitrary_requester_raw;
logic [NUM_REQ_W-1:0] ghost_rank_a;
logic [NUM_REQ_W-1:0] ghost_rank_b;
wire [NUM_REQ_W-1:0] ghost_base_a = chosen ? ghost_rank_a : next_requester_a;
wire [NUM_REQ_W-1:0] ghost_base_b = chosen ? ghost_rank_b : next_requester_b;
wire [NUM_REQ_W-1:0] ghost_next_a = (ghost_base_a == chosen_priority) ? NUM_REQ-1
        : (ghost_base_a > chosen_priority) ? ghost_base_a - 3'b1 : ghost_base_a;
wire [NUM_REQ_W-1:0] ghost_next_b = (ghost_base_b == chosen_priority) ? NUM_REQ-1
        : (ghost_base_b > chosen_priority) ? ghost_base_b - 3'b1 : ghost_base_b;
always @(posedge clk or posedge rst) begin
        if (rst) begin
                ghost_rank_a <= 3'b0;
                ghost_rank_b <= 3'b0;
        end
        else begin
                ghost_rank_a <= ghost_next_a;
                ghost_rank_b <= ghost_next_b;
        end
end
"""
L_TRACK_A: str = """
// L_track_a: once chosen, ghost_rank_a is the rank of arbitrary_requester
property ghost_tracks_a;
   @(posedge clk) disable iff (rst) chosen |-> ghost_rank_a == ranks[arbitrary_requester];
endproperty
"""
L_TRACK_B: str = """
// L_track_b: once chosen, ghost_rank_b is the rank of another_arbitrary_requester
property ghost_tracks_b;
   @(posedge clk) disable iff (rst) chosen |-> ghost_rank_b == ranks[another_arbitrary_requester];
endproperty
"""
L_GHOST: str = """
// L_ghost: once chosen, the two ghost ranks are in range and distinct
property ghost_ranks_distinct;
   @(posedge clk) disable iff (rst) chosen |-> (ghost_rank_a < NUM_REQ) && (ghost_rank_b < NUM_REQ)
        && (ghost_rank_a != ghost_rank_b);
endproperty
"""
REACH: str = """
// Nonvacuity: the target antecedent together with req[b] is reachable after reset release,
// on a trace that satisfies every assumed lemma of the DAG
property antecedent_unreachable;
   @(posedge clk) disable iff (rst) !(chosen & o_grant_vec_ref[arbitrary_requester] & in_req_vec[another_arbitrary_requester]);
endproperty
"""


class Harness(NamedTuple):
    """Lemma definitions appended to a model, the lemmas it assumes, and the one it asserts."""

    definitions: tuple[str, ...]
    assumed: tuple[str, ...]
    asserted: str


class LoopBodies(NamedTuple):
    min_step: str
    update_step: str


PROOF_DAG: dict[str, Harness] = {
    "sel": Harness((L_SEL,), (), "requesters_selected"),
    "init": Harness((L_INIT,), (), "ranks_reset_until_chosen"),
    "ghost": Harness((GHOST, L_GHOST), (), "ghost_ranks_distinct"),
    "track_a": Harness(
        (GHOST, L_INIT, L_SEL, L_TRACK_A), ("ranks_reset_until_chosen", "requesters_selected"), "ghost_tracks_a"
    ),
    "track_b": Harness(
        (GHOST, L_INIT, L_SEL, L_TRACK_B), ("ranks_reset_until_chosen", "requesters_selected"), "ghost_tracks_b"
    ),
    "ab": Harness(
        (GHOST, L_TRACK_A, L_TRACK_B, L_GHOST, L_AB),
        ("ghost_tracks_a", "ghost_tracks_b", "ghost_ranks_distinct"),
        "chosen_ranks_distinct",
    ),
    "target": Harness((L_SEL, L_AB), ("chosen_ranks_distinct", "requesters_selected"), "prop"),
}
WITNESSES: dict[str, Harness] = {
    "reach": Harness(
        (GHOST, L_INIT, L_SEL, L_TRACK_A, L_TRACK_B, L_GHOST, L_AB, REACH),
        tuple(h.asserted for name, h in PROOF_DAG.items() if name != "target"),
        "antecedent_unreachable",
    ),
}
STEP_MUTATIONS: dict[str, tuple[str, str]] = {
    "step1_mutant.sv": ("ranks[idx] < chosen_priority", "ranks[idx] > chosen_priority"),
    "step2_mutant.sv": ("ranks[idx] - 3'b1", "ranks[idx] + 3'b1"),
}
DISCOVERY_ON_REWRITTEN: dict[str, Harness] = {
    "perm": Harness((L_PERM,), (), "ranks_permutation"),
    "pair": Harness(
        (L_INIT, L_SEL, L_AB), ("ranks_reset_until_chosen", "requesters_selected"), "chosen_ranks_distinct"
    ),
    "target_perm": Harness((L_PERM, L_SEL), ("ranks_permutation", "requesters_selected"), "prop"),
    "plain": Harness((), (), "prop"),
}
DISCOVERY_ON_CUT: dict[str, Harness] = {
    "perm_cut": DISCOVERY_ON_REWRITTEN["perm"],
    "pair_cut": DISCOVERY_ON_REWRITTEN["pair"],
}

MODEL_HEADER: str = """module main
#(
   parameter  NUM_REQ   = {n},
   localparam NUM_REQ_W = (NUM_REQ > 1) ? $clog2(NUM_REQ+1) : 1
)
"""
STEP1_TEMPLATE: str = (
    MODEL_HEADER
    + """(
input  logic clk,
input  int idx,
input  logic [NUM_REQ-1:0] in_req_vec,
input  logic [NUM_REQ_W-1:0] chosen_priority_in,
input  logic [NUM_REQ*NUM_REQ_W-1:0] ranks_flat
);
default clocking @(posedge clk); endclocking

// Loop 1 relation R1: chosen_priority_o == chosen_priority_n and ranks_raw_o == ranks.
// From R1 before an iteration at any in-range idx, the original body (_o) and the rewritten body (_n)
// must re-establish R1.
logic [NUM_REQ_W-1:0] ranks [NUM_REQ-1:0];
logic [NUM_REQ_W-1:0] ranks_raw_o [NUM_REQ-1:0];
logic [NUM_REQ_W-1:0] chosen_priority_o;
logic [NUM_REQ_W-1:0] chosen_priority_n;
logic [NUM_REQ-1:0] ranks_raw_o_is_ranks;

for (genvar j = 0; j < NUM_REQ; j++) begin : g_rel
        assign ranks[j] = ranks_flat[j*NUM_REQ_W +: NUM_REQ_W];
        assign ranks_raw_o_is_ranks[j] = ranks_raw_o[j] == ranks[j];
end

always_comb begin
        chosen_priority_o = chosen_priority_in;
        ranks_raw_o = ranks;
{min_step_o}end

always_comb begin
        chosen_priority_n = chosen_priority_in;
{min_step_n}end

property min_step_keeps_r1;
   @(posedge clk) 0 <= idx && idx < NUM_REQ |-> chosen_priority_o == chosen_priority_n && &ranks_raw_o_is_ranks;
endproperty
assert property (min_step_keeps_r1);

endmodule
"""
)
STEP2_TEMPLATE: str = (
    MODEL_HEADER
    + """(
input  logic clk,
input  int idx,
input  logic [NUM_REQ-1:0] in_req_vec,
input  logic [NUM_REQ_W-1:0] chosen_priority_in,
input  logic [NUM_REQ*NUM_REQ_W-1:0] ranks_flat,
input  logic [NUM_REQ*NUM_REQ_W-1:0] ranks_raw_o_flat,
input  logic [NUM_REQ*NUM_REQ_W-1:0] ranks_raw_n_flat,
input  logic [NUM_REQ-1:0] o_grant_vec_raw_o_in,
input  logic [NUM_REQ-1:0] o_grant_vec_raw_n_in
);
default clocking @(posedge clk); endclocking

// Loop 2 relation R2(idx): chosen_priority_o == chosen_priority_n; entries j < idx of ranks_raw and
// o_grant_vec_raw agree between the original (_o) and rewritten (_n) blocks; entries j >= idx of the
// original still hold ranks[j] and 0. From R2(idx) at any in-range idx, one iteration of each body
// must establish R2(idx+1) and leave chosen_priority unchanged.
logic [NUM_REQ_W-1:0] ranks [NUM_REQ-1:0];
logic [NUM_REQ_W-1:0] ranks_raw_o_in [NUM_REQ-1:0];
logic [NUM_REQ_W-1:0] ranks_raw_n_in [NUM_REQ-1:0];
logic [NUM_REQ_W-1:0] ranks_raw_o [NUM_REQ-1:0];
logic [NUM_REQ-1:0]    o_grant_vec_raw_o;
logic [NUM_REQ_W-1:0] chosen_priority_o;
logic [NUM_REQ_W-1:0] ranks_raw_n [NUM_REQ-1:0];
logic [NUM_REQ-1:0]    o_grant_vec_raw_n;
logic [NUM_REQ_W-1:0] chosen_priority_n;
logic [NUM_REQ-1:0] related_before;
logic [NUM_REQ-1:0] related_after;

for (genvar j = 0; j < NUM_REQ; j++) begin : g_rel
        assign ranks[j] = ranks_flat[j*NUM_REQ_W +: NUM_REQ_W];
        assign ranks_raw_o_in[j] = ranks_raw_o_flat[j*NUM_REQ_W +: NUM_REQ_W];
        assign ranks_raw_n_in[j] = ranks_raw_n_flat[j*NUM_REQ_W +: NUM_REQ_W];
        assign related_before[j] = (j < idx)
                ? (ranks_raw_o_in[j] == ranks_raw_n_in[j] && o_grant_vec_raw_o_in[j] == o_grant_vec_raw_n_in[j])
                : (ranks_raw_o_in[j] == ranks[j] && !o_grant_vec_raw_o_in[j]);
        assign related_after[j] = (j < idx + 1)
                ? (ranks_raw_o[j] == ranks_raw_n[j] && o_grant_vec_raw_o[j] == o_grant_vec_raw_n[j])
                : (ranks_raw_o[j] == ranks[j] && !o_grant_vec_raw_o[j]);
end

always_comb begin
        chosen_priority_o = chosen_priority_in;
        ranks_raw_o = ranks_raw_o_in;
        o_grant_vec_raw_o = o_grant_vec_raw_o_in;
{update_step_o}end

always_comb begin
        chosen_priority_n = chosen_priority_in;
        ranks_raw_n = ranks_raw_n_in;
        o_grant_vec_raw_n = o_grant_vec_raw_n_in;
{update_step_n}end

property update_step_advances_r2;
   @(posedge clk) 0 <= idx && idx < NUM_REQ && &related_before
        |-> chosen_priority_o == chosen_priority_in && chosen_priority_n == chosen_priority_in && &related_after;
endproperty
assert property (update_step_advances_r2);

endmodule
"""
)
MITER_TEMPLATE: str = (
    MODEL_HEADER
    + """(
input  logic clk,
input  logic [NUM_REQ-1:0] in_req_vec,
input  logic [NUM_REQ*NUM_REQ_W-1:0] ranks_flat
);
default clocking @(posedge clk); endclocking

logic [NUM_REQ_W-1:0] ranks [NUM_REQ-1:0];
logic [NUM_REQ_W-1:0] ranks_raw_o [NUM_REQ-1:0];
logic [NUM_REQ-1:0]    o_grant_vec_raw_o;
logic [NUM_REQ_W-1:0] chosen_priority_o;
logic [NUM_REQ_W-1:0] ranks_raw_n [NUM_REQ-1:0];
logic [NUM_REQ-1:0]    o_grant_vec_raw_n;
logic [NUM_REQ_W-1:0] chosen_priority_n;
logic [NUM_REQ*NUM_REQ_W-1:0] next_ranks_o;
logic [NUM_REQ*NUM_REQ_W-1:0] next_ranks_n;

for (genvar k = 0; k < NUM_REQ; k++) begin : g_flat
        assign ranks[k] = ranks_flat[k*NUM_REQ_W +: NUM_REQ_W];
        assign next_ranks_o[k*NUM_REQ_W +: NUM_REQ_W] = ranks_raw_o[k];
        assign next_ranks_n[k*NUM_REQ_W +: NUM_REQ_W] = ranks_raw_n[k];
end

// original block (verbatim, outputs suffixed _o)
{original}
// rewritten block (outputs suffixed _n)
{rewritten}
property blocks_equivalent;
   @(posedge clk) chosen_priority_o == chosen_priority_n && o_grant_vec_raw_o == o_grant_vec_raw_n
        && next_ranks_o == next_ranks_n;
endproperty
assert property (blocks_equivalent);

endmodule
"""
)


def block_span(text: str) -> tuple[int, int]:
    return text.index(BLOCK_START), text.index(BLOCK_END) + len("end\n")


def original_block(text: str) -> str:
    start, stop = block_span(text)
    return text[start:stop]


def with_block(text: str, block: str) -> str:
    start, stop = block_span(text)
    return text[:start] + block + text[stop:]


def fill(skeleton: tuple[str, str, str], bodies: LoopBodies) -> str:
    head, middle, tail = skeleton
    return head + bodies.min_step + middle + bodies.update_step + tail


def loop_bodies(block: str) -> LoopBodies:
    """Split an always_comb block of the original shape into its two loop bodies."""
    head, middle, tail = ORIGINAL_SKELETON
    pattern: str = re.escape(head) + "(.*?)" + re.escape(middle) + "(.*?)" + re.escape(tail)
    match: re.Match[str] | None = re.fullmatch(pattern, block, re.DOTALL)
    if match is None:
        raise ValueError("benchmark always_comb block does not have the expected two-loop shape")
    return LoopBodies(match.group(1), match.group(2))


REWRITTEN_BODIES: LoopBodies = LoopBodies(MIN_STEP, UPDATE_STEP)
REWRITTEN_BLOCK: str = fill(REWRITTEN_SKELETON, REWRITTEN_BODIES)


def with_size(text: str, n: int) -> str:
    assert text.count(PARAM_LINE) == 1
    return text.replace(PARAM_LINE, f"parameter  NUM_REQ   = {n},")


def with_harness(text: str, harness: str) -> str:
    assert text.count(MODULE_END) == 1
    return text.replace(MODULE_END, harness + "\n" + MODULE_END)


def with_cut_port(text: str) -> str:
    assert text.count(LAST_PORT) == 1
    return text.replace(LAST_PORT, CUT_PORT)


def with_suffix(code: str, suffix: str) -> str:
    """Rename the block's state variables so two copies of a block can coexist in one module."""
    return re.sub(r"\b(" + "|".join(BLOCK_STATE) + r")\b", r"\g<1>" + suffix, code)


def harness_text(harness: Harness) -> str:
    assumptions: str = "".join(f"assume property ({name});\n" for name in harness.assumed)
    return "".join(harness.definitions) + DIRECTIVES_HEADER + assumptions + f"assert property ({harness.asserted});\n"


def rewritten_model(source: str, n: int) -> str:
    return with_size(with_block(source, REWRITTEN_BLOCK), n)


def step_harnesses(original: LoopBodies, rewritten: LoopBodies, n: int) -> dict[str, str]:
    return {
        "step1.sv": STEP1_TEMPLATE.format(
            n=n,
            min_step_o=with_suffix(original.min_step, "_o"),
            min_step_n=with_suffix(rewritten.min_step, "_n"),
        ),
        "step2.sv": STEP2_TEMPLATE.format(
            n=n,
            update_step_o=with_suffix(original.update_step, "_o"),
            update_step_n=with_suffix(rewritten.update_step, "_n"),
        ),
    }


def with_mutation(text: str, mutation: tuple[str, str]) -> str:
    before, after = mutation
    assert text.count(before) == 1
    return text.replace(before, after)


def mutant_harnesses(source: str, n: int) -> dict[str, str]:
    """Negative controls: step miters against a rewritten body with one flipped comparison (must be refuted)."""
    mutant: LoopBodies = LoopBodies(
        with_mutation(MIN_STEP, STEP_MUTATIONS["step1_mutant.sv"]),
        with_mutation(UPDATE_STEP, STEP_MUTATIONS["step2_mutant.sv"]),
    )
    steps: dict[str, str] = step_harnesses(loop_bodies(original_block(source)), mutant, n)
    return {"step1_mutant.sv": steps["step1.sv"], "step2_mutant.sv": steps["step2.sv"]}


def proof_harnesses(source: str, n: int) -> dict[str, str]:
    rewritten: str = rewritten_model(source, n)
    nodes: dict[str, Harness] = PROOF_DAG | WITNESSES
    dag: dict[str, str] = {f"{name}.sv": with_harness(rewritten, harness_text(h)) for name, h in nodes.items()}
    return {
        "original.sv": with_harness(with_size(source, n), "assert property (prop);\n"),
        **dag,
        **step_harnesses(loop_bodies(original_block(source)), REWRITTEN_BODIES, n),
        "miter.sv": MITER_TEMPLATE.format(
            n=n,
            original=with_suffix(original_block(source), "_o"),
            rewritten=with_suffix(REWRITTEN_BLOCK, "_n"),
        ),
    }


def discovery_harnesses(source: str, n: int) -> dict[str, str]:
    rewritten: str = rewritten_model(source, n)
    cut: str = with_size(with_cut_port(with_block(source, CUT_STEP_BLOCK)), n)
    on_rewritten: dict[str, str] = {
        f"{name}.sv": with_harness(rewritten, harness_text(h)) for name, h in DISCOVERY_ON_REWRITTEN.items()
    }
    on_cut: dict[str, str] = {f"{name}.sv": with_harness(cut, harness_text(h)) for name, h in DISCOVERY_ON_CUT.items()}
    return on_rewritten | on_cut


def write_files(directory: Path, files: dict[str, str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (directory / name).write_text(text)


def main(out_dir: Path, sizes: list[int]) -> None:
    source: str = BENCHMARK.read_text()
    for n in sizes:
        write_files(out_dir / f"N{n}", proof_harnesses(source, n))
        write_files(out_dir / f"N{n}" / "discovery", discovery_harnesses(source, n))
        write_files(out_dir / f"N{n}" / "controls", mutant_harnesses(source, n))


if __name__ == "__main__":
    main(Path(sys.argv[1]), [int(arg) for arg in sys.argv[2:]])
