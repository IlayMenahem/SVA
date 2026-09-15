---
name: accelerate-sva-proofs
description: Accelerate formal proofs of existing SystemVerilog Assertions using verified helper lemmas, assume-guarantee decomposition, and checked abstractions. Use for slow or timed-out SVA proofs and proof-cost optimization with an existing RTL and prover setup.
---

# Accelerate SVA proofs

Reduce the total cost of proving the original target under its original supplied premises. Work directly with the project's RTL, assertions, harness, and prover commands. Prefer a small, replayable proof over a large collection of speculative lemmas.

## Establish the proof problem

Inspect the target, elaborated hierarchy, clock/reset and initial-state model, parameters, source lists, constraints, and existing proof scripts. Identify the backend, version, supported SVA semantics, available proof engines, and the command that reproduces the current result. Use project documentation and installed tool help for exact commands; do not invent vendor Tcl commands or translate temporal operators mechanically.

Separate supplied environmental premises from generated assumptions. Record the original property and premises before optimizing. A property described as valid is still subject to verifier confirmation; a concrete counterexample must be reported, not constrained away.

Establish or reuse a reproducible direct-proof baseline. Capture the resource budget, proof outcome, elapsed time, and available CPU/memory statistics. If no budget is supplied, use existing project limits; if none exist, obtain a limit before launching expensive runs. The paper's experimental constants are not general defaults.

## Choose and evaluate changes

1. Inspect the open obligations' cones of influence and verifier diagnostics. Form a concrete hypothesis about the bottleneck: induction strength, wide arithmetic, deep temporal dependencies, or irrelevant state crossing a module boundary.
2. Choose a promising local change from [proof strategies](references/strategies.md). Prioritize expected reduction in total proof cost, including the helper's own proof. Keep candidate alternatives and their measured outcomes; avoid repeating an unchanged failed action.
3. Add auxiliary assertions or proof configuration in isolated candidate files. Preserve design behavior, the original target, and supplied premises. Prove helper obligations before using them in a parent proof.
4. Run the existing verifier flow and interpret its actual report. Distinguish unbounded proof, bounded pass, counterexample, timeout, unknown, and setup failure. Read [correctness and feedback](references/correctness.md) before introducing assumptions or transformations, and when interpreting a counterexample.
5. Keep changes that improve the measured objective or unlock a previously unresolved target. Retract unproductive changes and invalidate dependent results. A timeout measures an unsuccessful attempt; it does not refute the obligation.

Apply only transformations that the available backend can express and validate. The paper's action categories are lemma addition, cutpoints, blackboxing, counter abstraction, and retraction; direct work need not use a typed-action protocol.

## Preserve proof validity

- Maintain an acyclic dependency graph. A parent may assume a generated child only after the child is proved in a compatible context; the target must never justify its own helpers.
- Treat generated interface assumptions as obligations at the enclosing scope. Preserve supplied premises explicitly, including their origin and scope.
- Give every cutpoint, blackbox, or abstraction explicit preservation/interface obligations. Discharge them before using the transformed proof. The preservation argument must establish that proving the transformed target implies the original target; use equivalence where appropriate, or a checked conservative abstraction.
- Preserve sampling, reset disabling, initialization, widths, signedness, and temporal semantics. Do not obtain a faster result by weakening the target or restricting legal traces.
- Recheck assumption consistency and vacuity with backend-supported checks. Report absent or inconclusive checks. Satisfiable assumptions alone do not establish that an antecedent is reachable.
- Invalidate affected results whenever RTL, assumptions, scripts, parameters, tool configuration, dependencies, or transformations change. A stale success report is not evidence for the current proof.

## Record and audit

Read [recording and audit](references/recording.md) when using the bundled helpers. The scripts require Python 3.9+ and no third-party packages; the timed run recorder requires POSIX process-group support.

- `scripts/record_run.py` executes an explicit argument list, enforces a timeout, and records inputs, logs, reports, and elapsed time in a fresh directory. It never infers a proof from an exit code.
- `scripts/audit_proof.py` checks dependency bookkeeping, evidence integrity, and current input hashes using a ledger based on `assets/proof-ledger.json`. It does not parse vendor reports or establish formal soundness.

Use lean-ctx for source reads, searches, and large diagnostic output when available. Keep exact source files and full verifier artifacts on disk; do not replace replay evidence with compressed summaries. Do not require lean-ctx in environments where it is absent.

## Finish and report

Replay the accepted proof from clean prover state using the recorded setup; verify helpers before parents and audit the complete target closure. Report any unchecked semantic obligations separately from bookkeeping success. If the backend is unavailable, provide candidate artifacts and precise replay instructions, and mark them unverified.

Report the final target status, dependency graph, assumptions and transformations, replay commands, and remaining obligations. Compare equivalent budgets and configurations. Count failed attempts, helper proofs, baseline acquisition, and final replay in the optimization cost; separate reusable proof replay cost from discovery cost. Report cumulative verifier CPU time when available, elapsed wall time, calls, and agent cost when measurable. Claim speedup only from comparable measurements; a baseline timeout supports a newly solved result, not an exact speedup ratio.

Stop at a completed proof or the agreed budget. On exhaustion, retain the best replayable candidate and explain what remains unresolved.
