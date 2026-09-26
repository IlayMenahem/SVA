"""Negative controls and nonvacuity witnesses for the lrg_arb_lrg proof DAG.

Each control derives from a generated obligation by one textual mutation and
has an expected verdict. Miter mutants must be refuted, so the miters do
compare the two blocks. Dropped-assumption controls show which DAG edges are
needed for 1-induction. L3 -> L2 is needed only when NUM_REQ is not a power of
two: the pair registers are clog2(NUM_REQ+1) bits wide, and the observed
verdicts match EBMC indexing ranks[] through the low clog2(NUM_REQ) index bits.
At a power of two every such index is valid, so L3's own hypothesis
ranks[a] != ranks[b] suffices. Otherwise an out-of-range a breaks the step.
BMC witnesses show that the target's antecedent (with req[b]) and L3's
antecedent are reachable under the assumptions each uses.
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from ebmc_runner import INDUCTION_1, ebmc_command, run_ebmc
from lrg_arb_rtl import replace_once
from obligations import Obligation, obligations

BMC_8: Final[tuple[str, ...]] = ("--bound", "8")

TARGET_WITNESS: Final[str] = (
    "assert property (@(posedge clk) disable iff (rst) !(chosen && o_grant_vec_ref[arbitrary_requester]"
    " && in_req_vec[another_arbitrary_requester]));\n"
)
CHOSEN_WITNESS: Final[str] = "assert property (@(posedge clk) disable iff (rst) !chosen);\n"


@dataclass(frozen=True)
class Control:
    name: str
    base: str
    old: str
    new: str
    engine: tuple[str, ...]
    expected: str
    expected_pow2: str | None = None

    def expected_at(self, num_req: int) -> str:
        is_pow2 = num_req & (num_req - 1) == 0
        return self.expected_pow2 if is_pow2 and self.expected_pow2 else self.expected


CONTROLS: Final[tuple[Control, ...]] = (
    Control(
        "mut_iter_min", "rw_iter_min",
        "ranks_raw_r[idx] < chosen_priority_r)", "ranks_raw_r[idx] > chosen_priority_r)",
        INDUCTION_1, "refuted",
    ),
    Control(
        "mut_iter_update", "rw_iter_update",
        "ranks_raw_r[idx] - 3'b1 : ranks_raw_r[idx]", "ranks_raw_r[idx] : ranks_raw_r[idx]",
        INDUCTION_1, "refuted",
    ),
    Control(
        "mut_block", "rw_block",
        "ranks_raw_r[idx_r] - 3'b1 : ranks_raw_r[idx_r]", "ranks_raw_r[idx_r] : ranks_raw_r[idx_r]",
        INDUCTION_1, "refuted",
    ),
    Control(
        "L3_without_L1", "L3_pair_ranks", "assume property (lemma_init);\n", "", INDUCTION_1, "inconclusive",
    ),
    Control(
        "L3_without_L2", "L3_pair_ranks", "assume property (lemma_pair_valid);\n", "", INDUCTION_1,
        "inconclusive", expected_pow2="proved",
    ),
    Control(
        "target_without_L2", "target", "assume property (lemma_pair_valid);\n", "", INDUCTION_1,
        "inconclusive",
    ),
    Control(
        "target_without_L3", "target", "assume property (lemma_pair_ranks);\n", "", INDUCTION_1,
        "inconclusive",
    ),
    Control(
        "target_without_helpers", "target",
        "assume property (lemma_pair_valid);\nassume property (lemma_pair_ranks);\n", "",
        INDUCTION_1, "inconclusive",
    ),
    Control(
        "mut_target", "target",
        "(ranks[arbitrary_requester] < ranks[another_arbitrary_requester]));\nendproperty",
        "(ranks[arbitrary_requester] > ranks[another_arbitrary_requester]));\nendproperty",
        BMC_8, "refuted",
    ),
    Control("witness_target_antecedent", "target", "assert property (prop);\n", TARGET_WITNESS, BMC_8, "refuted"),
    Control(
        "witness_L3_antecedent", "L3_pair_ranks", "assert property (lemma_pair_ranks);\n", CHOSEN_WITNESS,
        BMC_8, "refuted",
    ),
)


@dataclass(frozen=True)
class ControlResult:
    name: str
    num_req: int
    expected: str
    verdict: str
    wall_s: float
    cpu_s: float
    command: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.expected == self.verdict


def run_control(control: Control, base: Obligation, num_req: int, out_dir: Path, timeout_s: float) -> ControlResult:
    sv = out_dir / f"ctl_{control.name}.sv"
    sv.write_text(replace_once(base.text, control.old, control.new))
    command = ebmc_command(sv, base.uses_reset, control.engine)
    run = run_ebmc(command, timeout_s, sv.with_suffix(".log"))
    return ControlResult(
        control.name, num_req, control.expected_at(num_req), run.verdict, run.wall_s, run.cpu_s, command
    )


def run_controls(num_req: int, out_dir: Path, timeout_s: float) -> list[ControlResult]:
    bases = {obligation.name: obligation for obligation in obligations(num_req, with_block_miter=True)}
    out_dir.mkdir(parents=True, exist_ok=True)
    return [
        run_control(control, bases[control.base], num_req, out_dir, timeout_s)
        for control in CONTROLS
        if control.base != "rw_block" or num_req <= 6
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("num_req", type=int, nargs="+")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    results = [
        result
        for num_req in args.num_req
        for result in run_controls(num_req, Path(f"N{num_req}/controls"), args.timeout)
    ]
    args.out.write_text(
        json.dumps([asdict(result) | {"ok": result.ok} for result in results], indent=2) + "\n"
    )
    print("\n".join(
        f"N={r.num_req:<4} {r.name:<28} expected={r.expected:<13} got={r.verdict:<13} "
        f"{r.wall_s:8.2f}s {'ok' if r.ok else 'MISMATCH'}"
        for r in results
    ))
    sys.exit(0 if all(result.ok for result in results) else 1)


if __name__ == "__main__":
    main()
