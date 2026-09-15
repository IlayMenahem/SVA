# Selecting a proof change

Use verifier evidence to choose a candidate. State what becomes easier, what new obligations arise, and why their combined cost may be lower. These are hypotheses, not guaranteed accelerations.

| Observed difficulty | Candidate | What must be checked |
| --- | --- | --- |
| Induction reaches unreachable states | A local invariant linking relevant state | Establish the invariant from the original initial states, including reset behavior; prove the target with it only after discharge. |
| Target spans a pipeline or hierarchy boundary | Intermediate protocol/state lemmas | Match cycle alignment, validity, stalls, flushes, and reset; discharge interface premises at their owning scope. |
| Wide counter dominates the cone | Bounds or relations first; then a smaller abstract representation if supported | Preserve wraparound, saturation, enable/reset priority, comparisons, and all target-visible behavior through explicit obligations. |
| Large producer feeds a small consumer interface | A cutpoint or blackbox with an interface contract | Establish the producer's guarantees and enclosing assumptions; account for temporal correlations across outputs. |
| Repeated expensive subproofs | Reuse a discharged helper in compatible parent contexts | Record exact premises, scope, and source/configuration fingerprints; do not reuse under a weaker environment without reproof. |

Prefer a helper that captures a missing relationship over restating the target. Examples of useful relationships include occupancy bounds, pointer/occupancy consistency, valid-data alignment, and state exclusivity. Infer the actual invariant from RTL and counterexamples; no generic bound or protocol rule is automatically valid.

For decomposition, draw edges from a parent to the obligations it needs. First discharge leaves under supplied premises, then discharge parents using only justified dependencies. If two candidate helpers depend on one another, restructure or prove their conjunction independently; do not enter a cycle as two completed proofs.

For abstraction, distinguish added behaviors from removed behaviors. Extra behaviors may yield spurious counterexamples; removed legal behaviors can make an invalid target appear true. State the concrete-to-abstract relation and the property-preservation obligation explicitly. If the backend cannot check that obligation, keep the transformation exploratory and do not report the original target proved from it.

Measure helpers and transformations individually where useful. Preserve the direct baseline and best completed candidate. Avoid over-decomposition when many small obligations cost more to elaborate and solve than the original proof.

The manuscript proposes best-first search; in a direct prover workflow, keep a small ranked list of alternatives using expected benefit, new obligation cost, and observed results. No fixed beam width or number of helper lemmas is required.
