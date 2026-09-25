You are a Claude Code CLI proof-search agent running as model `claude-opus-5-5` for exactly one SystemVerilog benchmark: `lrg_arb_lrg_16`, verified with EBMC.

Use the repository-local `accelerate-sva-proofs` skill. Read its complete `SKILL.md` and the referenced correctness and recording instructions (`references/correctness.md`, `references/recording.md`) before proof work. Follow the helper-DAG, assumption discharge, isolated-candidate, recording, clean-replay, and audit requirements.

Use this exact experiment configuration:
`/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva/config-claude-opus55-lrg_arb_lrg_16.json`
It specifies `direct_induction_bound=4`, a 120-second verifier-call cap, 720 seconds for discovery, and a 300-second clean-replay reserve. Do not silently change those settings. Every accepted k-induction proof must use bound 4 (other allowed engines: ic3, bdd).

Scope and fixed paths:
- Repository: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA`
- Experiment: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva`
- Fresh run root: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva/runs/claude-opus55-lrg_arb_lrg_16`
- Task directory: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva/runs/claude-opus55-lrg_arb_lrg_16/tasks/lrg_arb_lrg_16`
- Isolated workspace: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva/runs/claude-opus55-lrg_arb_lrg_16/tasks/lrg_arb_lrg_16/workspace`
- Original source: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/datasets/raw/large-lemma-miners/benchmarks/hard/lrg_arb_lrg_16_ebmc.sv`
- EBMC: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva/vendor/hw-cbmc/src/ebmc/ebmc`
- Backend: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva/tool_backend.py` (see also `verifier.py`, `core.py`)
- Recorder: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/accelerate-sva-proofs/scripts/record_run.py`
- Auditor: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/accelerate-sva-proofs/scripts/audit_proof.py`

The run is prepared and its direct bound-4 k-induction baseline has already timed out after 120 seconds. Inspect `baseline-direct.json`, `inventory.json`, and the baseline proof-run logs first. Preserve the original benchmark byte-for-byte. Put all new edits, harnesses, replay scripts, ledgers, and result files only under the task directory or workspace.

Conduct an independent run: do not read, copy, or rely on results from any other directory under `experiments/pi-headroom-sva/runs/`. You may inspect repository source code and the skill, but prior agents' proof artifacts are out of scope.

Parameter-generic proof (required): the design is parameterized by `NUM_REQ`. Write the helper lemmas generically in `NUM_REQ` (use generate loops / parameter-dependent expressions, not hard-coded 16-specific constants) so the same proof applies to `lrg_arb_lrg_N` for other N. Provide an executable replay script `replay/replay.sh` (or `.py`) in the task directory that takes `N` as an argument, instantiates the original source with `NUM_REQ=N` (by parameter override, not by editing the original file), runs the full accepted proof DAG from clean state, and prints per-obligation and total verifier wall time. Replay it for N=16 from clean state.

You may use structured backend actions or custom recorded verifier commands. Only completed unbounded proofs discharge obligations. Prove generated assumptions independently, record transformation/preservation obligations, keep the DAG acyclic, and review reset, initialization, widths, sampling, consistency, and antecedent reachability. Source-level normalization or abstraction is acceptable only with explicit preservation reasoning and obligations. Run independent obligations in parallel when useful and time-limit every verifier call.

Persist autonomously until the target has a clean replay and passing audit, or until useful in-scope approaches are exhausted. Leave `proof-ledger.json`, `audit-result.json`, and `CLAUDE-RESULT.md` in the task directory. The result must include exact replay commands, verifier timing/calls, DAG, assumptions, transformations, semantic caveats, and remaining obligations. Do not merely propose a plan.
