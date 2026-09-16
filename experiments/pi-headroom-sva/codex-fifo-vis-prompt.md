You are the proof-search agent for exactly one SystemVerilog benchmark: `fifo_vis`.

Use the repository-local `accelerate-sva-proofs` skill. Read its complete `SKILL.md` and the referenced strategy, correctness, and recording instructions before proof work. Follow the helper-lemma DAG, assume-guarantee, isolation, recording, clean-replay, and audit requirements faithfully.

This run replaces the campaign's Pi agent and Headroom service with Codex GPT-6 Astra and lean-ctx. Do not start Pi, Headroom, or make provider/API calls. Route shell commands through `lean-ctx -c`, file reads through `lean-ctx`-wrapped commands, and searches through `lean-ctx`-wrapped `rg`. Preserve full native proof evidence on disk.

Scope and fixed inputs:

- Repository: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA`
- Experiment: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva`
- Run root: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva/runs/codex-astra-high-fifo-vis`
- Task: `fifo_vis`
- Original source: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/datasets/raw/large-lemma-miners/benchmarks/hard/fifo_vis.sv`
- Isolated workspace: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva/runs/codex-astra-high-fifo-vis/tasks/fifo_vis/workspace`
- EBMC: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva/vendor/hw-cbmc/src/ebmc/ebmc`
- Backend: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/experiments/pi-headroom-sva/tool_backend.py`
- Recorder: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/accelerate-sva-proofs/scripts/record_run.py`
- Auditor: `/Users/ilaymenahem/Documents/university.nosync/Reasearch/SVA/accelerate-sva-proofs/scripts/audit_proof.py`

The campaign state is already prepared, and the ordinary direct k-induction baseline is run before you begin. Inspect its recorded result and evidence first. You may call the structured backend from the experiment directory by piping one JSON request into `python3 tool_backend.py`; every request must contain the run root, task `fifo_vis`, and an action. Its actions are `read_task`, `submit_candidate`, `invoke_ebmc`, `inspect_evidence`, and `retract_candidate`. Structured helpers are optional: custom harnesses and recorded verifier commands are allowed when necessary.

Keep the benchmark source unchanged. Put all experimental edits, scripts, ledgers, and replay artifacts in the isolated task workspace or task run directory. Do not alter unrelated files. Only completed unbounded proofs discharge obligations; bounded results are filters. Generated assumptions must be independently proved and must appear in an acyclic dependency DAG. Review reset, initial-state, width, sampling, assumption consistency, and antecedent reachability semantics.

Use no more than 120 seconds for any verifier call. Stop proof discovery within 720 seconds overall, preserving the best replayable candidate even if unresolved. If you establish the target, perform a clean unbounded replay, create `proof-ledger.json`, run the auditor, and leave a concise `CODEX-RESULT.md` in the task directory with exact replay commands, elapsed/verifier timing, calls, DAG, assumptions, transformations, semantic caveats, and remaining obligations. If not proved, still leave `CODEX-RESULT.md` and all evidence with an explicit unresolved-obligation account.

Begin now and continue until the clean replay and audit complete or useful in-scope options are exhausted.
