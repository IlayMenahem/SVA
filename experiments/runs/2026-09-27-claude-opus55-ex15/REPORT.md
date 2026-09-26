# ex15 (Large Lemma Miners, hard): accelerated Jasper proof

Target: `property prop` in `datasets/raw/large-lemma-miners/benchmarks/hard/ex15_ebmc.sv`,
`@(posedge clk) disable iff (rst) (state != DONE || n <= 0 || m < n)`, WIDTH = 32.
The benchmark declares `prop` without asserting it; `formal/ex15_obligations.sv` asserts the same
expression through a checker bound into `ex15` (`formal/ex15_bind.sv`).

**Status: proved (unbounded), Jasper 2024.06p002 on vlsi-luna71. Audit bookkeeping passed.**

## DAG

| Obligation | Statement | Assumes | Engine | Engine time | jg wall / CPU |
|---|---|---|---|---|---|
| `h_x_le_n` | `x <= n` | nothing | Hp | 0.002 s | 3.3 s / 0.63 s |
| `h_m_lt_x` | `m == 0 \|\| m < x` | nothing | Hp | 0.005 s | 3.3 s / 0.63 s |
| `target` | `prop` | `h_x_le_n`, `h_m_lt_x` | Hp | 0.002 s | 3.4 s / 0.69 s |

Why it works: `n` is fixed after reset and the loop increments `x` only while `x < n`, so `x <= n`.
`m` is 0 or was set to an `x` that was then incremented without wrapping (`x < n`), so `m < x`.
In DONE with `n > 0`, `m == 0 < n` or `m < x <= n`. Each obligation is 1-inductive; the target
alone is not (EBMC `--k-induction --bound 1`: INCONCLUSIVE).

No abstractions or supplied premises. The helpers are standalone, so the DAG is acyclic.

Nonvacuity: under both assumptions, cover `c_done` (`state == DONE && n != 0 && m != 0`) is
covered in 5 cycles. Reset analysis leaves only `n` without a reset value (loaded from free `n_init`).

## Cost

| | Jasper |
|---|---|
| Original (paper, `sota_timings/jasper.json`, m6i.32xlarge) | 187 s |
| Original, rerun here | not completed (stopped after ~100 s, still in BMC trace attempts) |
| Accelerated, 3 obligations (sum of jg sessions) | 10.0 s wall, 1.95 s CPU; engine time < 0.01 s |

About 3.2 s of each session is Jasper startup; all three obligations fit in one session.

## WIDTH scaling (Jasper, engine time in seconds; all proven, Hp)

| WIDTH | h_x_le_n | h_m_lt_x | target |
|---|---|---|---|
| 32 | 0.002 | 0.005 | 0.002 |
| 64 | 0.008 | 0.038 | 0.003 |
| 256 | 0.096 | 0.088 | 0.017 |
| 1024 | 0.337 | 1.105 | 0.146 |
| 4096 | 9.13 | 22.8 | 3.65 |

Growth is polynomial in WIDTH (comparator size), not exponential; the same lemmas apply at every width.

## Replay

```sh
cd experiments/runs/2026-09-27-claude-opus55-ex15
formal/run_jasper.sh x_le_n 32
formal/run_jasper.sh m_lt_x 32
formal/run_jasper.sh target 32          # also proves cover c_done
sh formal/scaling.sh 64 256 1024 4096   # recorded width sweep
python3 build_ledger.py && python3 ../../../accelerate-sva-proofs/scripts/audit_proof.py proof-ledger.json
```

Run records: `proof-runs/<obligation>-w<WIDTH>/` (`run.json`, `stdout.log`, `stderr.log`).
The partial baseline run in `proof-runs/baseline-w32/` has no `run.json` (stopped).

Discovery cost: one EBMC precheck session (seconds), 3 + 12 recorded Jasper runs, and one partial
baseline run. Agent token cost was not measured.
