# Correctness and verifier feedback

## Inspect the actual proof context

Before treating a result as reusable, inspect the command/report and the assumptions active in that run. Match the intended target, elaboration, hierarchy, parameters, source and include files, macros, clocks, resets, initialization, engine mode, and relevant tool settings. Source hashes cannot detect an omitted include file or an unrecorded environment setting.

Preserve SVA sampling semantics, overlapping versus non-overlapping implication, sequence delays and repetition, strong/weak termination, and `$past` history availability. Do not equate reset disabling with an ordinary sampled antecedent. Check the backend's documented semantics when a construct is unsupported or ambiguous.

An explicit proof of a generated helper does not justify arbitrary uses of it: the parent's context must imply the helper's premises, and its clock/scope/instance must match. Inspect the actual assumptions loaded by the parent, not just those listed in the ledger. Generated assumptions need proofs at the enclosing scope; supplied environmental constraints need an identified source.

For each transformation, record the concrete and transformed objects, relation or interface contract, all preservation obligations, and every proof using it. Prove those obligations without relying circularly on the transformed target. Require a compatible context and complete dependency closure before accepting the original target.

## Interpret outcomes

| Backend observation | Response |
| --- | --- |
| Explicit completed unbounded proof | Record `proved` only after checking property identity, mode, context, and supporting obligations. |
| No violation through a finite bound | Record `bounded`; report the bound. It cannot discharge a dependency requiring an unbounded proof. |
| Concrete counterexample | Record `failed`; inspect the violating cycles, reset/history, and active assumptions. Report a false original target rather than repairing its specification silently. |
| Counterexample after abstraction | Check whether the trace is feasible in the concrete design. Refine the abstraction/contract if spurious; keep the obligation unresolved until rechecked. |
| Timeout or inconclusive engine result | Record `timeout` or `unknown`; use the reached depth/resource evidence to choose another candidate. |
| Parse, elaboration, license, or unsupported-feature error | Record `error`; repair the setup before reasoning about property validity. |

Keep complete traces on disk; inspect the relevant signal cone and cycles first. A local trace explanation is a debugging aid, not a proof certificate.

## Consistency, vacuity, and replay

Use available consistency/reachability checks for supplied and generated assumptions. Check relevant antecedent reachability and reset release rather than relying only on assertion success. An unreachable antecedent may be intended; document that fact and avoid attributing an optimization's speedup to newly introduced vacuity.

Changes to a helper, its premises, or a transformation invalidate dependent evidence even if the target text is unchanged. Re-run with the final configuration from clean prover state. Cached backend results may be reused only when their documented context validation is sufficient and their dependencies are available for replay.

The bundled auditor can find structural inconsistencies. It cannot establish that a lemma is true, an abstraction is conservative, a report was interpreted correctly, a manifest is complete, or a proof has no vacuity. These remain explicit verifier and engineering checks.

## Worked decisions

- **Useful lemma:** occupancy bounds are independently proved under the original reset model; a pointer-related target then proves faster using those bounds. Keep the lemma only after comparing combined cost, and record the target's actual use of it.
- **False lemma:** a proposed `count < DEPTH` fails when the queue is full. Inspect whether `count == DEPTH` is legal before revising the helper. Never add `count < DEPTH` as an environmental assumption to suppress the trace.
- **Spurious abstract trace:** blackboxing a producer permits output combinations its RTL cannot generate. Check trace feasibility, derive and prove an interface relation, then retry the consumer proof. Do not label the abstract counterexample a concrete design bug without that check.
