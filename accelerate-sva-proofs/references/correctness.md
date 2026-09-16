# Correctness and verifier feedback

## Proof context

Match each result to its actual target, elaboration, hierarchy, parameters, sources/includes, macros, assumptions, clocks, resets, initialization, and proof mode. A parent's context must imply its helpers' premises, with compatible scope and instances. Identify the source of supplied environmental premises; generated assumptions belong in the DAG.

Preserve SVA sampling, implication timing, sequence delays/repetition, strong/weak termination, and `$past` history. Reset disabling differs from a sampled antecedent. Check widths and signedness when transforming expressions or state.

Record each abstraction's concrete and transformed objects, relation or contract, preservation obligations, and uses. Validate these without circular reliance on the transformed target.

## Outcomes

| Observation | Response |
| --- | --- |
| Completed unbounded proof | Record `proved` for this obligation under its recorded dependencies; open dependencies keep the overall proof conditional. |
| No violation through a finite bound | Record `bounded` and the bound; this does not discharge an unbounded obligation. |
| Concrete counterexample | Record `failed`; inspect violating cycles, reset/history, and active assumptions. A failed helper may need revision; a false target must be reported. |
| Abstract counterexample | Check concrete feasibility; refine the abstraction or contract if spurious. |
| Timeout or inconclusive result | Record `timeout` or `unknown`; use depth/resource evidence to choose another candidate. |
| Parse, elaboration, license, or unsupported-feature error | Record `error` and repair the setup. |

Keep full traces on disk and inspect relevant signals and cycles first.

## Final validation

Check assumption consistency, antecedent reachability, and reset release: satisfiable assumptions alone do not establish nonvacuity. Document intended unreachable antecedents.

Changes to RTL, premises, helpers, abstractions, or configuration invalidate affected evidence. Recheck dependent results in the final context; reuse cached results only with sufficient context validation and replayable dependencies.

The auditor checks bookkeeping and evidence integrity, not lemma truth, abstraction soundness, report interpretation, manifest completeness, or nonvacuity.
