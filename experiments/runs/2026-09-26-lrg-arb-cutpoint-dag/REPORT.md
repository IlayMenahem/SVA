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

## Free-variable variant (gen_free.py, sweep_free.sh)

- The harness gets two symbolic constants `free_i`, `free_j`: registers with no reset that hold their arbitrary initial value forever.
- A lemma proven at `free_i`/`free_j` holds for every index. It can therefore be assumed at any index expression; the target assumes it at its own `a`, `b`.
- This replaces the per-index enumeration. Obligations go from Θ(N²) to **6**, and Q/A are no longer needed.

| session | asserts | assumes | model |
|---|---|---|---|
| F1 | R(i): `i<N \|-> ranks[i]<N`, C | none | cp cut |
| F2 | D(i,j): `i,j<N && i!=j \|-> ranks[i]!=ranks[j]` | R(i), R(j) | cp cut |
| F3 | G(i), M(j) | none | **concrete** |
| F4 | target, cover W_grant_req | G(a), M(b), D(a,b), C | cp cut |

- Controls (both cex at every N):
  - X1: `ranks[free_i] < N-1`. This shows `free_i` really ranges over the indices.
  - X3: the target without M(b). This shows the cp relation lost by the cut is needed.
  - Dropping G instead is *not* a valid control. G holds structurally even with cp cut, and the target still proves without it.

### Benchmark: free-variable vs enumerated DAG (DAG sessions only, same host, `{Hp Mp N}`, JOBS=6)

| N | free: obligations | free: wall | free: CPU | enumerated: lemmas | enumerated: wall | enumerated: CPU |
|---|---|---|---|---|---|---|
| 16 | 6 | 3.3 s | 3.5 s | 426 | 6.5 s | 6.8 s |
| 32 | 6 | 4.0 s | 5.6 s | 1618 | 7.2 s | 19.9 s |
| 64 | 6 | 8.2 s | 19.7 s | 6306 | 22.3 s | 140.8 s |
| 128 | 6 | 23.2 s | 76.0 s | 24898 | 143.5 s | 1762 s |
| 256 | 6 | 104.4 s | 443.5 s | 98946 | 1121 s | 16360 s |

- CPU speedup over the enumerated DAG grows with N: 7× at 64, 23× at 128, 37× at 256. Wall speedup at 256 is 10.7×.
- Total CPU per doubling is N^1.95 (64→128) and N^2.55 (128→256); the enumerated DAG was about N^3.2.
- Most of the wall time at small N is Jasper startup, about 3 s per session.
- Per-session CPU (s):

| N | F1 | F2 (D, cut) | F3 (G/M, concrete) | F4 |
|---|---|---|---|---|
| 64 | 0.8 | 15.4 | 2.6 | 0.9 |
| 128 | 0.9 | 60.2 | 13.8 | 1.0 |
| 256 | 1.3 | 303.0 | 137.9 | 1.5 |

  - F2 is the largest cost. It grows about N^2.0, then N^2.3.
  - F3 is growing fastest: N^2.4, then N^3.3. It runs on the concrete design, where the N-way min feeds the symbolically indexed grant.
  - F1 and F4 stay at Jasper startup cost.
  - Wall time is roughly max(F2, F3), because sessions run in parallel.
- Raw logs: `sweep_free.txt` and `sweep_free_big.txt`, kept local.

## Toward N log N (gen_nlogn.py, `VARIANT=nlogn sh sweep_free.sh`)

In gen_free.py, D (an N-state induction over `ranks[free_i]`) and M (an N-step transitivity chain behind `chosen_priority`) dominate. Engine and cut choices (e.g. `Hp` with `stopat ranks` for G/M) buy a constant factor, not a better slope.

### Localised lemmas

Both global arguments become local, O(1)-step arguments over auxiliary harness logic. The RTL is unchanged.

- **D via shadows.** `sh_i` and `sh_j` equal `free_i` and `free_j` in the first cycle after reset. After that they apply the RTL's per-index update, `rank_upd(r, cp)`.
  - Jasper leaves no-reset registers X during reset, so a reset-loaded shadow is unrelated to `free_i`. The shadow is therefore selected by a `started` flag.
  - S_i and S_j (`ranks[free_x] == sh_x`) are single-index inductions.
  - DS says the 2-register shadow system stays distinct and in range.
  - D then follows combinationally from S and DS.
- **M via a snapshot walker.** `min_chain` is the RTL's comparator chain as a module. It is instantiated twice:
  - on (`ranks`, `in_req_vec`), giving `rpm`, with EQ: `rpm[N] == cp` (ranks cut; structural);
  - on frozen symbolic snapshots (`snap_r`, `snap_q`: no-reset hold registers, like `free_i`), giving `spm`.

  A walker (`wk`, `wacc`) folds the snapshot one position per cycle. This turns the N-step transitivity into the 1-step invariant WI:
  `wk<=N && wacc==spm[wk] && (free_j<wk && snap_q[free_j] -> wacc<=snap_r[free_j])`.
  - MS: at `wk==N`, `spm[N] <= snap_r[free_j]` for requesting `free_j`.
  - The snapshot is an arbitrary constant, and `wk` reaches N deterministically. So MS gives the combinational fact PHI(v, y) for every valuation v. PHI is assumed at v = (`ranks`, `in_req_vec`), y = `free_j`. This is the same instantiation rule already used for `free_i`/`free_j`.
  - M is then combinational from EQ and PHI.

| session | asserts | assumes | model |
|---|---|---|---|
| P_C | C | none | cp cut |
| P_Si, P_Sj | S_i, S_j | none | cp cut |
| P_DS | DS | none | cp cut |
| P_D | D(i,j) | S_i, S_j, DS | cp cut |
| P_G | G(i) | none | ranks cut |
| P_EQ | EQ | none | ranks cut |
| P_WI | WI | none | concrete |
| P_MS | MS | WI | concrete |
| P_M | M(j) | EQ, PHI(real, j) | ranks cut |
| P_T | target, cover W_grant_req | G(a), M(b), D(a,b), C | cp cut |

- Engine: `Hp` for all DAG sessions.
- Controls are cex at every N:
  - X1 (`ranks[free_i] < N-1`);
  - X3 (target without M);
  - X4 (MS with a strict `<`, which checks that the walker invariant is not vacuous).
- The X4 cover `wk == N` is reached, and so is the target's cover W_grant_req.

### Result (sweep_nlogn.txt, kept local; CPU s; DAG sessions only; JOBS=6)

| N | total CPU | exp | P_Si | P_Sj | P_WI | max other | wall (incl. controls) |
|---|---|---|---|---|---|---|---|
| 16 | 7.9 | | 0.8 | 0.8 | 0.7 | 0.8 | 9.5 |
| 32 | 8.4 | 0.08 | 0.9 | 0.9 | 0.9 | 0.8 | 9.6 |
| 64 | 9.7 | 0.22 | 1.2 | 1.2 | 1.1 | 0.8 | 9.7 |
| 128 | 13.2 | 0.44 | 2.2 | 2.2 | 1.8 | 1.0 | 10.3 |
| 256 | 30.2 | 1.19 | 8.1 | 8.1 | 4.7 | 1.3 | 14.7 |
| 512 | 56.8 | 0.91 | 14.2 | 14.2 | 12.2 | 2.7 | 22.3 |
| 1024 | 190.2 | 1.74 | 52.3 | 52.0 | 49.4 | 7.0 | 58.3 |

- **Against gen_free.py at N=256:** CPU drops from 443.5 s to 30.2 s (14.7×). Wall drops from 104.4 s to 14.7 s.
- **N=512 and N=1024** were out of reach before, and now take 22 s and 58 s wall.
- **Growth.** Over 256→1024, total CPU grows 6.3×, which is an exponent of 1.33. N log N predicts 5× (1.16) and N² predicts 16×.
  - Up to N=512 the measurements are consistent with N log N.
  - The 512→1024 doubling is 1.74.
- **Not strictly N log N yet.**
  - Eight of the eleven sessions (C, DS, D, G, EQ, MS, M, T) stay at 7 s or less at N=1024. From 256 to 1024 they grow about N^1, which is Jasper startup/elaboration of the O(N log N) netlist.
  - The residual super-N log N term comes from the three sessions that still induct through a symbolically indexed mux: S_i and S_j (`ranks[free_i]`), and WI (`spm[wk]`, `snap_r[wk]`). Each grows about N^1.9 from 512 to 1024.
- **Tried: per-index split of S.**
  - The split is N asserts `free_i==k |-> ranks[k]==sh_i`, each with an O(log N) cone of influence, and D is then proven from the 2N instances.
  - It is sound, and D stays cheap (10.0 s at 1024).
  - The split session costs 1.6 / 6.5 / 11.9 / 38.9 s at N = 64 / 256 / 512 / 1024, i.e. the same slope.
  - The remaining term therefore appears to be Jasper's per-design/per-property overhead on the O(N log N) netlist, not the proof itself. The mux form was kept.
  - `Ht` on the split did not finish within 600 s at N=64.
