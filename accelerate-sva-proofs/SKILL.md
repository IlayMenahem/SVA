---
name: accelerate-sva-proofs
description: Accelerate formal proofs of existing SystemVerilog Assertions by composing helper-lemma DAGs, assume-guarantee reasoning, and abstractions. Use for slow or timed-out SVA proofs and proof-cost optimization with an existing RTL and prover setup.
---

# Accelerate SVA proofs

Reduce total proof cost by composing three strategies:

1. **Helper-lemma DAG:** represent proof obligations as nodes, with edges from each obligation to the helpers it assumes.
2. **Assume-guarantee reasoning:** prove local guarantees under interface assumptions, assigning generated assumptions to obligations at their owning scope.
3. **Abstractions:** replace expensive state or logic with a simpler model and add its preservation obligations to the DAG. State the concrete-to-abstract relation and why proving the abstract target implies the concrete one. Common abstractions include cutpoints (stopat), initial value abstraction, counter abstractions, and blackboxing.

Different helper lemmas can have its own abstractions and be proved with a different proof engine.

To evaluate how a proof or a lemma scales (i.e., how its CPU time grows with parameter size: exponential, polynomial, linear, logarithmic, and constant), shrink large parameters and observe the CPU time.
The lower in the heirarchy the CPU time grows, the better; the proof should be accepted for the original parameters.

Helpers may be assumed to prove other helpers or the target before they are proved. Results remain conditional until every obligation in the target's dependency closure is validated; execution order need not follow the DAG.

## Workflow

1. Inspect the target's cone, RTL, harness, clock/reset, initial states, parameters, supplied premises, and proof commands. Use diagnostics to identify the bottleneck.
2. Choose compositions from [Compositions](#compositions) by the estimated combined cost of the target and new obligations; many small obligations can cost more than the original proof. Keep a small ranked list of candidates.
3. Evaluate candidates in isolated files, using [correctness and feedback](references/correctness.md) to interpret results and check proof contexts.
4. Retain improvements and replay the accepted proof from clean prover state. On budget exhaustion, preserve the best replayable candidate and list unresolved obligations.

## Compositions


| Difficulty | Composition | Key obligations |
| --- | --- | --- |
| Induction admits unreachable states | Invariant helpers for bounds, state exclusivity, or pointer/occupancy relations | Initialization and preservation under transitions. |
| Target spans a pipeline or hierarchy boundary | Local guarantees under interface assumptions | Cycle alignment, validity, stalls, flushes, and reset. |
| Expensive logic drives a small interface | Cutpoints constrained by helper contracts | The concrete drivers satisfy the contracts, including temporal correlations. |
| Initial-state detail dominates reasoning | Initial value abstraction that retains relevant relations | The abstract initial set includes every legal concrete initial state and preserves required cross-state relations. |
| Wide counters dominate the cone | Bound/relation helpers, then smaller abstract counters | Wraparound, saturation, enable/reset priority, comparisons, and target-visible behavior. |

## Evidence and reporting

Use [recording and audit](references/recording.md) for the bundled run recorder and DAG auditor. Keep exact inputs, commands, and full proof artifacts on disk.

Report target status, the dependency DAG, abstractions, and replay commands. Compare equivalent configurations and budgets, separating discovery cost (including failed attempts and baseline acquisition) from reusable proof cost (including helpers and preservation obligations). Report elapsed time, verifier CPU time, calls, and agent cost: the API cost, or an estimate from API pricing and token usage.

## Work methodology

- Time-limit each lemma proof attempt; with the right assumptions and abstractions, each lemma should prove within seconds to a minute.
- Use free variables and bit splitting to simplify proofs and let the proof engine do its optimizations.
- Schedule obligations by expected payoff, running the prover on several in parallel.
