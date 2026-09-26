"""Text transformations of the lrg_arb_lrg benchmark RTL.

The benchmark's `always_comb` block has `if` statements inside two unrolled
`for` loops. EBMC 6.0 synthesizes each `if` into a phi node that is not cut into
a wire, so `chosen_priority`/`ranks_raw` expressions grow exponentially in
NUM_REQ. `ternary_rewrite` replaces each `if` with the equivalent
conditional-operator assignments, which EBMC cuts into one auxiliary wire per
assignment, making the transition relation linear in NUM_REQ.
"""

import re
from pathlib import Path
from typing import Final

REPO: Final[Path] = Path(__file__).resolve().parents[3]
BENCHMARK: Final[Path] = (
    REPO / "datasets/raw/large-lemma-miners/benchmarks/hard/lrg_arb_lrg_16_ebmc.sv"
)

PARAMETER_LINE: Final[str] = "   parameter  NUM_REQ   = 16,\n"

LOOP_HEADER: Final[str] = "        for (idx=0; idx < NUM_REQ; idx++) begin\n"
LOOP_FOOTER: Final[str] = "        end\n"

ORIGINAL_MIN_BODY: Final[str] = (
    "                if (in_req_vec[idx] && ranks_raw[idx] < chosen_priority) begin\n"
    "                        chosen_priority = ranks_raw[idx];\n"
    "        \n"
    "                end\n"
)
TERNARY_MIN_BODY: Final[str] = (
    "                chosen_priority = (in_req_vec[idx] && ranks_raw[idx] < chosen_priority)"
    " ? ranks_raw[idx] : chosen_priority;\n"
)
ORIGINAL_UPDATE_BODY: Final[str] = (
    "                if (ranks_raw[idx] == chosen_priority) begin\n"
    "                        o_grant_vec_raw[idx] = 1'b1;\n"
    "                        ranks_raw[idx] = NUM_REQ-1;\n"
    "                end else if (ranks_raw[idx] > chosen_priority) begin\n"
    "                        ranks_raw[idx] = ranks_raw[idx] - 3'b1;\n"
    "                end\n"
)
TERNARY_UPDATE_BODY: Final[str] = (
    "                o_grant_vec_raw[idx] = (ranks_raw[idx] == chosen_priority)"
    " ? 1'b1 : o_grant_vec_raw[idx];\n"
    "                ranks_raw[idx] = (ranks_raw[idx] == chosen_priority) ? NUM_REQ-1\n"
    "                               : ((ranks_raw[idx] > chosen_priority)"
    " ? ranks_raw[idx] - 3'b1 : ranks_raw[idx]);\n"
)

COMB_BLOCK_START: Final[str] = "always_comb begin\n"
COMB_BLOCK_END: Final[str] = "end\nlogic chosen;\n"

TARGET_ENDPROPERTY: Final[str] = (
    "        |-> (~in_req_vec[another_arbitrary_requester] || "
    "(ranks[arbitrary_requester] < ranks[another_arbitrary_requester]));\n"
    "endproperty\n"
)

COMB_STATE: Final[tuple[str, ...]] = ("ranks_raw", "chosen_priority", "o_grant_vec_raw")


def loop(body: str) -> str:
    """Wrap a loop body in the benchmark's `for (idx...)` header and footer."""
    return LOOP_HEADER + body + LOOP_FOOTER


def replace_once(text: str, old: str, new: str) -> str:
    """Replace the unique occurrence of `old`; fail if it is absent or repeated."""
    count = text.count(old)
    if count != 1:
        raise ValueError(f"expected exactly one occurrence, found {count}: {old[:60]!r}")
    return text.replace(old, new)


def original_rtl(num_req: int) -> str:
    """The benchmark text with only the NUM_REQ default changed."""
    if num_req < 2:
        raise ValueError("NUM_REQ must be at least 2")
    return replace_once(
        BENCHMARK.read_text(),
        PARAMETER_LINE,
        f"   parameter  NUM_REQ   = {num_req},\n",
    )


def ternary_rewrite(rtl: str) -> str:
    """Apply the if-to-conditional-operator rewrite to both comb loops."""
    return replace_once(
        replace_once(rtl, loop(ORIGINAL_MIN_BODY), loop(TERNARY_MIN_BODY)),
        loop(ORIGINAL_UPDATE_BODY),
        loop(TERNARY_UPDATE_BODY),
    )


def insert_after_target(rtl: str, harness: str) -> str:
    """Insert helper declarations and directives right after `property prop`."""
    return replace_once(rtl, TARGET_ENDPROPERTY, TARGET_ENDPROPERTY + harness)


def comb_block_body(rtl: str) -> str:
    """The statements of the unique `always_comb` block of the benchmark."""
    start = rtl.index(COMB_BLOCK_START) + len(COMB_BLOCK_START)
    return rtl[start : rtl.index(COMB_BLOCK_END, start)]


def suffix_names(text: str, names: tuple[str, ...], suffix: str) -> str:
    """Append `suffix` to every whole-word occurrence of `names` in `text`."""
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b")
    return pattern.sub(lambda match: match.group(1) + suffix, text)
