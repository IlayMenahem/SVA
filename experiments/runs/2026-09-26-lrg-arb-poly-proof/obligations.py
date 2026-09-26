"""Generate the SVA proof obligations for lrg_arb_lrg_N.

Dependency DAG (edges point from an obligation to the helpers it assumes):

    target        -> L2_pair_valid, L3_pair_ranks
    L3_pair_ranks -> L1_init, L2_pair_valid
    L1_init, L2_pair_valid: no dependencies

The lemmas and the target are proved on the rewritten model (see lrg_arb_rtl).
The rewrite has two obligations checked per N: rw_iter_min and rw_iter_update
prove that each `if` loop body equals its conditional-operator form from every
pre-state and every idx < NUM_REQ. Since both comb loops are sequences of such
bodies, the whole comb blocks are equal. rw_block is the direct whole-block
miter, feasible only for small N because it synthesizes the original block.
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from lrg_arb_rtl import (
    BENCHMARK,
    COMB_STATE,
    ORIGINAL_MIN_BODY,
    ORIGINAL_UPDATE_BODY,
    REPO,
    TERNARY_MIN_BODY,
    TERNARY_UPDATE_BODY,
    comb_block_body,
    insert_after_target,
    original_rtl,
    suffix_names,
    ternary_rewrite,
)

RUN_DIR: Final[Path] = Path(__file__).resolve().parent
GENERATOR_FILES: Final[tuple[Path, ...]] = (RUN_DIR / "lrg_arb_rtl.py", Path(__file__).resolve())

LEMMA_HARNESS: Final[str] = """
logic ranks_is_init;
always_comb begin
        int kdx;
        ranks_is_init = 1'b1;
        for (kdx=0; kdx < NUM_REQ; kdx++) begin
                ranks_is_init = (ranks[kdx] == kdx) ? ranks_is_init : 1'b0;
        end
end

property lemma_init;
   @(posedge clk) disable iff (rst) ~chosen |-> ranks_is_init;
endproperty

property lemma_pair_valid;
   @(posedge clk) disable iff (rst) chosen
        |-> (arbitrary_requester != another_arbitrary_requester)
            && (arbitrary_requester < NUM_REQ) && (another_arbitrary_requester < NUM_REQ);
endproperty

property lemma_pair_ranks;
   @(posedge clk) disable iff (rst) chosen
        |-> (ranks[arbitrary_requester] < NUM_REQ) && (ranks[another_arbitrary_requester] < NUM_REQ)
            && (ranks[arbitrary_requester] != ranks[another_arbitrary_requester]);
endproperty

"""

LEMMA_DAG: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "L1_init": ("lemma_init", ()),
    "L2_pair_valid": ("lemma_pair_valid", ()),
    "L3_pair_ranks": ("lemma_pair_ranks", ("lemma_init", "lemma_pair_valid")),
    "target": ("prop", ("lemma_pair_valid", "lemma_pair_ranks")),
}

MITER_HEADER: Final[str] = """module main
#(
   parameter  NUM_REQ   = {num_req},
   localparam NUM_REQ_W = (NUM_REQ > 1) ? $clog2(NUM_REQ+1) : 1
)
(
input  logic clk,
input  logic [NUM_REQ-1:0]  in_req_vec,
{ports}
);

"""

MITER_STATE_DECLS: Final[str] = """logic [NUM_REQ_W-1:0] ranks_raw{s} [NUM_REQ-1:0];
logic [NUM_REQ-1:0]    o_grant_vec_raw{s};
logic [NUM_REQ_W-1:0] chosen_priority{s};
"""

MITER_CHECK: Final[str] = """
logic ranks_raw_equal;
always_comb begin
        int kdx;
        ranks_raw_equal = 1'b1;
        for (kdx=0; kdx < NUM_REQ; kdx++) begin
                ranks_raw_equal = (ranks_raw_o[kdx] == ranks_raw_r[kdx]) ? ranks_raw_equal : 1'b0;
        end
end

assert property ((chosen_priority_o == chosen_priority_r)
        && (o_grant_vec_raw_o == o_grant_vec_raw_r) && ranks_raw_equal);

endmodule
"""

ITER_PORTS: Final[str] = """input  logic [31:0] idx,
input  logic [NUM_REQ_W-1:0] chosen_priority_in,
input  logic [NUM_REQ-1:0]  o_grant_vec_raw_in,
input  logic [NUM_REQ*NUM_REQ_W-1:0] ranks_raw_in"""

ITER_BLOCK: Final[str] = """always_comb begin
        int jdx;
        chosen_priority{s} = chosen_priority_in;
        o_grant_vec_raw{s} = o_grant_vec_raw_in;
        for (jdx=0; jdx < NUM_REQ; jdx++) begin
                ranks_raw{s}[jdx] = ranks_raw_in >> (jdx*NUM_REQ_W);
        end
{body}end

"""

BLOCK_PORTS: Final[str] = "input  logic [NUM_REQ*NUM_REQ_W-1:0] ranks_in"

BLOCK_INPUT: Final[str] = """logic [NUM_REQ_W-1:0] ranks [NUM_REQ-1:0];
always_comb begin
        int jdx;
        for (jdx=0; jdx < NUM_REQ; jdx++) begin
                ranks[jdx] = ranks_in >> (jdx*NUM_REQ_W);
        end
end

"""


@dataclass(frozen=True)
class Obligation:
    name: str
    text: str
    uses_reset: bool


def lemma_directives(asserted: str, assumed: tuple[str, ...]) -> str:
    assumes = "".join(f"assume property ({name});\n" for name in assumed)
    return assumes + f"assert property ({asserted});\n"


def lemma_obligation(num_req: int, name: str) -> Obligation:
    asserted, assumed = LEMMA_DAG[name]
    harness = LEMMA_HARNESS + lemma_directives(asserted, assumed)
    text = insert_after_target(ternary_rewrite(original_rtl(num_req)), harness)
    return Obligation(name, text, uses_reset=True)


def iteration_miter(num_req: int, name: str, original_body: str, ternary_body: str) -> Obligation:
    blocks = "".join(
        MITER_STATE_DECLS.format(s=suffix) for suffix in ("_o", "_r")
    ) + "".join(
        ITER_BLOCK.format(s=suffix, body=suffix_names(body, COMB_STATE, suffix))
        for suffix, body in (("_o", original_body), ("_r", ternary_body))
    )
    text = (
        MITER_HEADER.format(num_req=num_req, ports=ITER_PORTS)
        + blocks
        + "assume property (idx < NUM_REQ);\n"
        + MITER_CHECK
    )
    return Obligation(name, text, uses_reset=False)


def block_miter(num_req: int) -> Obligation:
    original = original_rtl(num_req)
    names = COMB_STATE + ("idx",)
    blocks = "".join(
        MITER_STATE_DECLS.format(s=suffix)
        + "always_comb begin\n"
        + suffix_names(comb_block_body(rtl), names, suffix)
        + "end\n\n"
        for suffix, rtl in (("_o", original), ("_r", ternary_rewrite(original)))
    )
    text = MITER_HEADER.format(num_req=num_req, ports=BLOCK_PORTS) + BLOCK_INPUT + blocks + MITER_CHECK
    return Obligation("rw_block", text, uses_reset=False)


def obligations(num_req: int, with_block_miter: bool) -> list[Obligation]:
    rewrite = [
        iteration_miter(num_req, "rw_iter_min", ORIGINAL_MIN_BODY, TERNARY_MIN_BODY),
        iteration_miter(num_req, "rw_iter_update", ORIGINAL_UPDATE_BODY, TERNARY_UPDATE_BODY),
    ] + ([block_miter(num_req)] if with_block_miter else [])
    return rewrite + [lemma_obligation(num_req, name) for name in LEMMA_DAG]


def manifest(obligation_file: Path, num_req: int, uses_reset: bool) -> dict[str, object]:
    files = (obligation_file, BENCHMARK, *GENERATOR_FILES)
    return {
        "files": [str(path.relative_to(REPO)) for path in files],
        "settings": {
            "top": "main",
            "reset": "main.rst" if uses_reset else None,
            "engine": "ebmc --k-induction --bound 1",
            "NUM_REQ": num_req,
        },
    }


def write_obligation(out_dir: Path, num_req: int, obligation: Obligation) -> Path:
    path = out_dir / f"{obligation.name}.sv"
    path.write_text(obligation.text)
    (out_dir / f"{obligation.name}.manifest.json").write_text(
        json.dumps(manifest(path, num_req, obligation.uses_reset), indent=2) + "\n"
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("num_req", type=int)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--block-miter", action="store_true", help="add rw_block (small N only)")
    args = parser.parse_args()
    out_dir: Path = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [
        write_obligation(out_dir, args.num_req, obligation)
        for obligation in obligations(args.num_req, args.block_miter)
    ]
    print("\n".join(str(path) for path in paths))


if __name__ == "__main__":
    main()
