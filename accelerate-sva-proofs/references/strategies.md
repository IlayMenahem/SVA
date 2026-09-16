# Composing proof strategies

Build a helper-lemma DAG around the expensive relationships in the target's cone. Use assume-guarantee contracts to separate local reasoning, then abstract logic or state behind those contracts. Choose candidates by expected combined proof cost; too many small obligations can cost more than the original proof.

| Difficulty | Composition | Key obligations |
| --- | --- | --- |
| Induction admits unreachable states | Add invariant helpers for bounds, state exclusivity, or pointer/occupancy relations | Initialization and preservation under transitions. |
| Target spans a pipeline or hierarchy boundary | Split into local guarantees and interface assumptions | Cycle alignment, validity, stalls, flushes, and reset; discharge generated interface assumptions at their owning scope. |
| Expensive logic drives a small interface | Introduce cutpoints constrained by helper contracts | The concrete drivers satisfy the contracts, including temporal correlations. |
| Initial-state detail dominates reasoning | Abstract initial values while retaining relevant relations | The abstract initial set includes every legal concrete initial state and preserves required cross-state relations. |
| Wide counters dominate the cone | Prove bounds/relations and replace counters with smaller abstract representations | Wraparound, saturation, enable/reset priority, comparisons, and target-visible behavior. |
| A large module contributes little relevant behavior | Blackbox its implementation behind an assume-guarantee contract | The module satisfies the contract under the enclosing premises. |

State each abstraction's concrete-to-abstract relation and why a proof of the abstract target implies the concrete target. Added behaviors may cause spurious counterexamples; removing legal behaviors can conceal failures.

Schedule obligations by expected payoff, even when their dependencies remain open. If helpers depend on one another, restructure the decomposition or prove their conjunction as one obligation. Reuse helpers only where scope, clocks, and premises are compatible.
