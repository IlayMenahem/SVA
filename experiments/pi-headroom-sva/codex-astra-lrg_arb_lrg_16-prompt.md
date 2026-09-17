You are a Codex CLI proof-search agent running as model `gpt-6-astra` for exactly one SystemVerilog benchmark: `lrg_arb_lrg_16`.

Use the repository-local `accelerate-sva-proofs` skill. Read its complete `SKILL.md` and referenced strategy, correctness, and recording instructions before proof work. Follow the helper-DAG, assumption discharge, isolated-candidate, recording, clean-replay, and audit requirements.

This run replaces Pi with Codex GPT-6 Astra and uses lean-ctx. Do not start Pi or make OpenRouter calls. Route shell commands through `lean-ctx -c`, file reads through lean-ctx-wrapped commands, and searches through lean-ctx-wrapped `rg`. Preserve complete native proof evidence on disk.

Use this exact experiment configuration:
`/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva/config-codex-astra-lrg_arb_lrg_16.json`

It currently specifies `model=gpt-6-astra`, `reasoning_effort=high`, `direct_induction_bound=4`, a 120-second verifier-call cap, 720 seconds for discovery, and a 300-second clean-replay reserve. Do not silently change those settings. Every accepted k-induction proof must use bound 4.

Scope and fixed paths:

- Repository: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA`
- Experiment: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva`
- Fresh run root: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva/runs/codex-astra-agent-lrg_arb_lrg_16`
- Task directory: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva/runs/codex-astra-agent-lrg_arb_lrg_16/tasks/lrg_arb_lrg_16`
- Isolated workspace: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva/runs/codex-astra-agent-lrg_arb_lrg_16/tasks/lrg_arb_lrg_16/workspace`
- Original source: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/datasets/raw/large-lemma-miners/benchmarks/hard/lrg_arb_lrg_16_ebmc.sv`
- EBMC: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva/vendor/hw-cbmc/src/ebmc/ebmc`
- Backend: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva/tool_backend.py`
- Recorder: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/accelerate-sva-proofs/scripts/record_run.py`
- Auditor: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/accelerate-sva-proofs/scripts/audit_proof.py`

The run is prepared and its direct bound-4 baseline has already timed out after 120 seconds during front-end synthesis. Inspect its `baseline-direct.json`, `run.json`, and logs first. Preserve the original benchmark byte-for-byte. Put all new edits, harnesses, replay scripts, ledgers, and result files only under the fresh task directory or workspace.

Conduct an independent run: do not read, copy, or rely on results from any other directory under `experiments/pi-headroom-sva/runs/`. You may inspect repository source code and the skill, but prior agents' proof artifacts are out of scope.

You may use structured backend actions or custom recorded verifier commands. Only completed unbounded proofs discharge obligations. Prove generated assumptions independently, record transformation/preservation obligations, keep the DAG acyclic, and review reset, initialization, widths, sampling, consistency, and antecedent reachability. Source-level normalization or abstraction is acceptable only with explicit preservation reasoning and obligations.

Persist autonomously until the target has a clean replay and passing audit, or until useful in-scope approaches are exhausted. Leave `proof-ledger.json`, `audit-result.json`, and `CODEX-RESULT.md` in the task directory. The result must include exact replay commands, verifier timing/calls, DAG, assumptions, transformations, semantic caveats, and remaining obligations. Do not merely propose a plan.
