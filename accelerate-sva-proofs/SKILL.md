---
name: accelerate-sva-proofs
description: Accelerate formal proofs of existing SystemVerilog Assertions by composing helper-lemma DAGs, assume-guarantee reasoning, and abstractions. Use for slow or timed-out SVA proofs and proof-cost optimization with an existing RTL and prover setup.
---

# Accelerate SVA proofs

Reduce total proof cost by composing three strategies:

1. **Helper-lemma DAG:** represent proof obligations as nodes, with edges from each obligation to the helpers it assumes.
2. **Assume-guarantee reasoning:** prove local guarantees under interface assumptions, assigning generated assumptions to obligations at their owning scope.
3. **Abstractions:** simplify expensive state or logic using cutpoints, initial value abstraction, counter abstractions, and blackboxing; include preservation and interface obligations in the DAG.

Helpers may be assumed before they are proved. Results remain conditional until every obligation in the target's dependency closure is validated; execution order need not follow the DAG.

## Workflow

1. Inspect the target's cone, RTL, harness, clock/reset, initial states, parameters, supplied premises, and proof commands. Use diagnostics to identify the bottleneck.
2. Choose a composition from [strategies](references/strategies.md), estimating the combined cost of the target and new obligations. Keep a small ranked list of candidates.
3. Evaluate candidates in isolated files, using [correctness and feedback](references/correctness.md) to interpret results and check proof contexts.
4. Retain improvements and replay the accepted proof from clean prover state. On budget exhaustion, preserve the best replayable candidate and list unresolved obligations.

## Backend support

Not every backend supports every strategy, SVA construct, or validation check. Check available capabilities and documented semantics before choosing a technique. Report unsupported or inconclusive checks; an abstraction with unvalidated preservation obligations remains exploratory.

## Evidence and reporting

Use [recording and audit](references/recording.md) for the bundled run recorder and DAG auditor. Keep exact inputs, commands, and full proof artifacts on disk.

Report target status, the dependency DAG, assumptions, abstractions, replay commands, and remaining obligations. Compare equivalent configurations and budgets, separating discovery cost (including failed attempts and baseline acquisition) from reusable proof cost (including helpers and preservation obligations). Report elapsed time, verifier CPU time, calls, and agent cost when available.
