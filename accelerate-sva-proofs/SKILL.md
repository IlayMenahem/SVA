---
name: accelerate-sva-proofs
description: Accelerate formal proofs of existing SystemVerilog Assertions by composing helper-lemma DAGs, assume-guarantee reasoning, and abstractions. Use for slow or timed-out SVA proofs.
---

# Accelerate SVA proofs

Reduce total CPU time by composing three strategies:

1. **Helper-lemma DAG:** represent proof obligations as nodes, with edges from each obligation to the helpers it assumes.
2. **Assume-guarantee reasoning:** prove local guarantees under interface assumptions, assigning generated assumptions to obligations at their owning scope.
3. **Abstractions:** replace expensive state or logic with a simpler model and add its preservation obligations to the DAG. State the concrete-to-abstract relation and why proving the abstract target implies the concrete one. Common abstractions include cutpoints (stopat), initial value abstraction, counter abstractions, and blackboxing.

Helpers may be assumed to prove other helpers or the target before they are proved. Results remain conditional until every obligation in the target's dependency closure is validated; execution order need not follow the DAG.

## Workflow

1. **Baseline:** Inspect the target's cone, RTL, harness, clock/reset, initial states, parameters, supplied premises, and proof commands. Run the target under a time limit with the run recorder to record baseline CPU time, and use diagnostics to identify the bottleneck. If the baseline finished then you completed your task.
2. **Shrink:** If parameters are large, derive a reduced configuration for fast iteration (see [Scaling](#scaling)).
3. **Propose:** Choose compositions from [Compositions](#compositions) by the estimated combined cost of the target and new obligations; many small obligations can cost more than the original proof. Keep a small ranked list of candidates. For each candidate, draft its DAG nodes, and for each abstraction, its concrete-to-abstract relation.
4. **Evaluate:** Run candidates in isolated files under time limits, several at once, ordered by expected payoff. Interpret results and check proof contexts with [correctness and feedback](references/correctness.md). Measure how each lemma scales, only up to the target's parameter size.
5. **Integrate:** Keep improvements, update the DAG, and audit that every obligation in the target's dependency closure is proved.
6. **Replay:** Replay the accepted proof at the original parameters from clean prover state. If the budget runs out, keep the best replayable candidate and list the unresolved obligations.
7. **Report:** Follow [Evidence and reporting](#evidence-and-reporting).

## Compositions

| Difficulty | Composition | Key obligations |
| --- | --- | --- |
| Induction admits unreachable states | Invariant helpers for bounds, state exclusivity, or pointer/occupancy relations | Initialization and preservation under transitions. |
| Target spans a pipeline or hierarchy boundary | Local guarantees under interface assumptions | Cycle alignment, validity, stalls, flushes, and reset. |
| Expensive logic drives a small interface | Cutpoints constrained by helper contracts | The concrete drivers satisfy the contracts, including temporal correlations. |
| Initial-state detail dominates reasoning | Initial value abstraction that retains relevant relations | The abstract initial set includes every legal concrete initial state and preserves required cross-state relations. |
| Wide counters dominate the cone | Bound/relation helpers, then smaller abstract counters | Wraparound, saturation, enable/reset priority, comparisons, and target-visible behavior. |

## Scaling

If our module has a large parameter size, we first would work on the module with the shrink the parameters, writing a proof that will be accepted fast for the original parameters.
To evaluate how a proof or a lemma scales (i.e., how its CPU time grows with parameter size: exponential, polynomial, linear, logarithmic, and constant).
The lower in the heirarchy the CPU time grows, the better.
If the number of lemmas is constant, the scaling of the proof is the scaling of the worst scaling lemma.

Note: we want to minimize the total CPU time (Proof discovery + final validation), so you shouldn't try to check scaling beyond the target's parameter size.

## Evidence and reporting

Use [recording and audit](references/recording.md) for the bundled run recorder and DAG auditor.

Report the dependency DAG, abstractions, and replay commands.

At the top of the report there should be listed the following statistics:
- Whether the target was proved
- Agent time cost: the API cost, or an estimate from API pricing and token usage.
- discovery CPU time (including failed attempts and baseline acquisition)
- proof CPU time (including helpers and preservation obligations).
- number of verifier calls
- Proof DAG size and depth, and number of abstractions

## General advice and notes

- Time-limit each lemma proof attempt; with the right assumptions and abstractions, each lemma should prove within seconds to minutes.
- Use free variables and bit splitting to simplify proofs and let the proof engine do its optimizations. Bit splitting can allow for parallelization.
- Schedule obligations by expected payoff, running the prover on several in parallel.
- Different helper lemmas can have its own abstractions and be proved with a different proof engine.
