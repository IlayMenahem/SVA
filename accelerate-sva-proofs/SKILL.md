---
name: accelerate-sva-proofs
description: Accelerate formal proofs of existing SystemVerilog Assertions by composing helper-lemma DAGs, assume-guarantee reasoning, and abstractions. Use for slow or timed-out SVA proofs.
---

# Accelerate SVA proofs

Reduce total CPU time by composing three strategies:

1. **Helper-lemma DAG:** represent proof obligations as nodes, with edges from each obligation to the helpers it assumes.
2. **Assume-guarantee reasoning:** prove local guarantees under interface assumptions, assigning generated assumptions to obligations at their owning scope.
3. **Abstractions:** replace expensive state or logic with a simpler model and add its preservation obligations to the DAG. Common abstractions include cutpoints (stopat), initial value abstraction, counter abstractions, and blackboxing.

## Workflow

1. **Baseline:** Inspect the target's cone, RTL, harness, clock/reset, initial states, parameters, supplied premises, and proof commands. While continuing with the next steps, check that the target isn't trivial with a short recorded run (about 60 s). If it proves, or a counterexample shows it is false, you completed your task.
2. **Bottleneck identification:** Use the baseline run's diagnostics to identify the bottleneck; its CPU time is the baseline CPU time.
3. **Shrink:** If parameters are large, derive a reduced configuration for fast iteration (see [Scaling](#scaling)).
4. **DAG build:** Build a DAG of obligations and abstractions layer by layer, top to bottom, starting with the target. Each layer is a set of obligations and abstractions that can be proved with k-induction (k<=4) assuming only the layers below it; the bottom layer assumes only supplied premises.
5. **Replay:** Replay the proof at the original parameters in one recorded session from clean prover state: each node with the single engine that proved it fastest, independent nodes in parallel, and each node assuming only its proved dependencies. The proof is accepted only if [`validate_proof.py`](references/recording.md#validate-a-proof) passes.
6. **Report:** Follow [Evidence and reporting](#evidence-and-reporting).

## Compositions

| Difficulty | Composition | Key obligations |
| --- | --- | --- |
| Induction admits unreachable states | Invariant helpers for bounds, state exclusivity, or pointer/occupancy relations; try the design's own assertions first | Initialization and preservation under transitions. |
| Arithmetic compared across register stages | Symbolic-constant operands (rigid free registers) with a reference model evaluated on them | Every concrete violation maps to an abstract one with the constants set to its operands. |
| Wide arithmetic identity | Bit splitting, MSB first for division, each bit assuming the bits already proved | Every bit proved; the split covers the whole word. |
| Target depends on few control signals | Cut those signals, constrained by a lemma proved on the concrete design | The lemma holds without assuming the target or the cut. |
| Target spans a pipeline or hierarchy boundary | Local guarantees under interface assumptions | Cycle alignment, validity, stalls, flushes, and reset. |
| Expensive logic drives a small interface | Cutpoints constrained by helper contracts | The concrete drivers satisfy the contracts, including temporal correlations. |
| Initial-state detail dominates reasoning | Initial value abstraction that retains relevant relations | The abstract initial set includes every legal concrete initial state and preserves required cross-state relations. |
| Wide counters dominate the cone | Bound/relation helpers, then smaller abstract counters | Wraparound, saturation, enable/reset priority, comparisons, and target-visible behavior. |

## Scaling

If our module has a large parameter size, we first work on the module with shrunk parameters, writing a proof that will be accepted fast for the original parameters.
Evaluate how a proof or a lemma scales, i.e., how its CPU time grows with parameter size: exponential, polynomial, linear, logarithmic, or constant.
The lower in the hierarchy the CPU time grows, the better.
The scaling of a proof is the sum of the scaling of the lemmas; take into account whether the number of lemmas grows with the parameter size.

Note: we want to minimize the total CPU time (Proof discovery + final validation), so you shouldn't try to check scaling beyond the target's parameter size.

## Evidence and reporting

Use [recording and validation](references/recording.md) for the bundled run recorder and proof validator.

Report the dependency DAG, abstractions, and replay commands.

At the top of the report there should be listed the following statistics:
- Whether the target was proved
- Agent time cost: the API cost, or an estimate from API pricing and token usage.
- wall time: the total time from the start of your run to the end of the replay, or of the baseline if it settles the target.
- discovery CPU time (including failed attempts and baseline acquisition)
- proof CPU time (including helpers and preservation obligations).
- number of verifier calls
- Proof DAG size and depth, and number of abstractions

## General advice and notes

- Time-limit each lemma proof attempt; with the right assumptions and abstractions, each lemma should prove within seconds to minutes.
- Use free variables and bit splitting to simplify proofs and let the proof engine do its optimizations. Bit splitting can allow for parallelization.
- Schedule obligations by expected payoff, running the prover on several in parallel.
- Different helper lemmas can have its own abstractions and be proved with a different proof engine.
