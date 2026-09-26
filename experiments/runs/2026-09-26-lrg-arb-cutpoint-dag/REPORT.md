# lrg_arb_lrg_N: cutpoint + lemma DAG proof (Jasper)

## Target status

`prop` (lrg_arb_lrg_16_ebmc.sv:91-94) is **proven (unbounded)** for N = 16. Also proven for N = 32, 64, 128 and 256 by the same generator.

- `audit_proof.py proof-ledger-N16.json`:
  - `bookkeeping_ok: true`
  - `errors: []`
  - closure = 426 obligations
  - `formal_validity: not_certified`. This is the audit tool's fixed stance; it checks the bookkeeping, not the logic.
- The negative controls give cex, as expected, in every run.
- The `W_grant_req` witness and the target's precondition cover are covered, so the target is not vacuous.

## Proof DAG (gen.py)

`cp` = `chosen_priority`, the combinational min over the requesters' ranks. `a` = `arbitrary_requester`, `b` = `another_arbitrary_requester`.

| id | statement | assumes | model |
|---|---|---|---|
| R_i | `ranks[i] < N` | none | cp cut |
| C | `chosen \|-> a<N && b<N && a!=b` | none | cp cut |
| D_i_j | `ranks[i] != ranks[j]` | R_i, R_j | cp cut |
| G_i | `grant[i] \|-> ranks[i] == cp` | none | **concrete** |
| M_j | `req[j] \|-> cp <= ranks[j]` | none | **concrete** |
| Q_i_j | `grant[i] && req[j] \|-> ranks[i] < ranks[j]` | G_i, M_j, D_ij | cp cut |
| A_j | `chosen && grant[a] && req[j] && a!=j \|-> ranks[a] < ranks[j]` | Q_*_j | cp cut |
| target | `prop` | A_*, C | cp cut |

- The number of obligations is O(N²). Each Jasper session assumes exactly the union of the dependencies of its asserts.
- Sessions are packed greedily up to 1024 (asserts + assumptions), and all sessions are independent. The ledger's session names are therefore scheduling only.
- The DAG sessions run `set_engine_mode {Hp Mp N}`; the controls run `{Hp B Ht}`.

### Abstraction and preservation

- `stopat chosen_priority` turns cp into a free input. This is an over-approximation, so any property proven with the cut holds on the concrete design.
- The cut loses the relation between cp and ranks/requests. The lemmas that need that relation (Q_i_j) assume the contracts G_i and M_j, which are proven on the **uncut** design.
- In the ledger these contracts are recorded as preservation obligations:
  - `cut_cp_grant_i` and `cut_cp_min_j` list obligations [G_i] / [M_j];
  - each of those obligations is a dependency of every Q that uses the cut.
- Control X3 (Q_0_1 with only D_0_1 assumed) gives **cex**, so the contracts are necessary.
- Control X1 (`ranks[i] < N-1`) gives **cex**, so the harness is not over-constrained.

### Harness adaptation

- `NUM_REQ` is set with `elaborate -parameter`.
- `int idx;` is hoisted to the top of the `always_comb` block. Verific rejects a declaration after statements; the move does not change semantics.
- `target: assert property (prop);` is appended.
- `rst` is declared with Jasper `reset rst`, and the source's own `disable iff (rst)` is kept.

## Replay

```
sh replay.sh 16                         # gen -> ship to vlsi -> run_levels.sh (xargs -P 6) -> RESULT lines
python3 ../../../accelerate-sva-proofs/scripts/record_run.py --cwd . --manifest inputs.json \
  --output proof-runs/N16-final --timeout 3600 --tool-version 'Jasper 2024.06p002' -- /bin/sh replay.sh 16
python3 build_ledger.py 16 proof-runs/N16-final/run.json
python3 ../../../accelerate-sva-proofs/scripts/audit_proof.py proof-ledger-N16.json
sh sweep.sh "16 32 64 128 256" X1 X3 > sweep.txt && python3 summarize.py sweep.txt   # scaling
```

- Host: vlsi, 20 cores, shared with other users. Jasper Apps 2024.06p002.
- CPU is `/usr/bin/time` user+sys of `jg -batch`. It counts only engine processes that jg reaped, so it may undercount; the baseline was measured the same way. Wall times are noisy because the host is shared.

## Cost: N = 16, same host and tool

| config | wall | verifier CPU | Jasper calls |
|---|---|---|---|
| baseline: `prove -all`, auto engines, no helpers | 249.0 s | 1850.6 s | 1 |
| DAG replay (recorded, 6 sessions) | 7.3 s (9.6 s incl. ssh/transfer) | 10.3 s | 6 |
| + negative controls X1, X3 | +0 s (parallel) | 2.5 s | 2 |

- The speedup is about 34× in wall time and about 180× in CPU.
- The dataset's reference time for N = 16 is 907 s.

## Scaling (sweep.txt, kept local per runs/.gitignore; DAG sessions only, controls excluded)

| N | sessions | lemmas proven | wall | verifier CPU |
|---|---|---|---|---|
| 16 | 6 | 426 | 6.5 s | 6.8 s |
| 32 | 7 | 1618 | 7.2 s | 19.9 s |
| 64 | 19 | 6306 | 22.3 s | 140.8 s |
| 128 | 65 | 24898 | 143.5 s | 1762 s |
| 256 | 277 | 98946 | 1121 s | 16360 s |

- There are Θ(N²) obligations, each over a model whose size is polynomial in N.
- Measured CPU grows roughly like N^3 (N^2.8, N^3.6, N^3.2 per doubling from 32 to 256). Most of it is in L5: each A_j assumes N-1 Q lemmas and muxes over `a`.
- The baseline has no such bound. At N = 16 it already costs 1850 CPU-s.

## Discovery vs reusable cost

**Reusable proof cost** is the recorded replay above: all helpers and preservation obligations, about 10 CPU-s at N = 16.

**Discovery cost**, all on vlsi:
- Baseline acquisition: 249 s wall / 1850 CPU-s.
- A first DAG with the target in a single session with O(N²) assumptions. It proved N ≤ 64 but hit the 1800 s session limit at N = 128. This led to the Q/A/L6 split and sharding.
- Ablations at N = 16:
  - without D: target proved in 41.7 s;
  - D without R: proved in 4.2 s.
  - So R and D are cost helpers, not logical necessities.
- Sweep 2, with auto engines and 16 concurrent sessions: 62.7 s wall / 779 CPU-s for N = 16–64. N = 128 was aborted and later cleaned up.
- Sweep 3, the final settings: about 1300 s wall / 18 300 CPU-s for N = 16–256.
- Roughly 1.5 h of wall time on the shared host overall.

**Agent cost**:
- This is an estimate, not a metered API bill.
- About 2 context windows and roughly 300 tool calls.
- Order of 15–20 M cached input tokens and about 0.15 M output tokens.
- At Opus-class list pricing this is roughly US$30–50.
