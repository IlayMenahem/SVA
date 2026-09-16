# SVA campaign report

## Status

Campaign status: `prepared`. Method solves count only after clean replay and ledger audit.

| Method | Solved |
|---|---:|
| method | 0 |
| ric3 | 13 |
| jasper | 25 |
| vcf | 14 |

## Tasks solved beyond published baselines

- ric3: none
- jasper: none
- vcf: none

## Cost and compression

Reconciled API charges: `$0` across 0 requests. Actual routed providers: none recorded.
Headroom compressed 0 evidence retrievals; recorded tokens: 0 before and 0 after.

## Per-task outcomes

| Task | Method | Discovery s | Replay s | rIC3 (s) | JasperGold (s) | VCF (s) |
|---|---|---:|---:|---|---|---|
| buffer_128 | missing | — | — | proved (0.06) | timeout | timeout |
| buffer_32 | missing | — | — | proved (0.01) | proved (188) | timeout |
| buffer_64 | missing | — | — | proved (0.03) | proved (435) | timeout |
| counter_66 | missing | — | — | timeout | timeout | proved (15) |
| dp | missing | — | — | timeout | proved (6) | timeout |
| ex15 | missing | — | — | timeout | proved (187) | timeout |
| ex3 | missing | — | — | timeout | proved (54) | proved (1) |
| ex4 | missing | — | — | timeout | proved (3) | proved (1) |
| ex51_57_1 | missing | — | — | timeout | proved (6) | timeout |
| ex51 | missing | — | — | timeout | proved (4) | proved (2) |
| ex80 | missing | — | — | timeout | proved (2340) | timeout |
| fifo_ref_16 | missing | — | — | proved (0.04) | timeout | timeout |
| fifo_ref_64 | missing | — | — | proved (0.15) | timeout | timeout |
| fifo_vis | missing | — | — | proved (619.63) | proved (1580) | proved (8664) |
| gr2006 | missing | — | — | proved (275.51) | proved (820) | proved (1) |
| gulwani_cegar2_1 | missing | — | — | proved (123.82) | proved (287) | timeout |
| gulwani_cegar2_2 | missing | — | — | proved (119.36) | proved (356) | timeout |
| gulwani_cegar2_3 | missing | — | — | timeout | proved (233) | timeout |
| gulwani_cegar2_4 | missing | — | — | timeout | proved (218) | timeout |
| gulwani_cegar2_5 | missing | — | — | timeout | timeout | timeout |
| gulwani_cegar2 | missing | — | — | timeout | proved (187) | timeout |
| gulwani_fig1a_2 | missing | — | — | timeout | proved (853) | proved (1) |
| gulwani_fig1a_4 | missing | — | — | timeout | proved (613) | proved (1) |
| gulwani_fig1a_5 | missing | — | — | timeout | proved (192) | proved (1) |
| gulwani_fig1a_6 | missing | — | — | timeout | timeout | proved (1) |
| gulwani_fig1a | missing | — | — | timeout | proved (192) | proved (1) |
| lrg_arb_lrg_16 | missing | — | — | timeout | proved (907) | proved (750) |
| lrg_arb_lrg_4 | missing | — | — | proved (0.02) | proved (3) | proved (1) |
| lrg_arb_lrg_8 | missing | — | — | proved (2.55) | proved (5) | proved (2) |
| simple_cam_16 | missing | — | — | proved (0.06) | proved (188) | timeout |
| simple_cam_8 | missing | — | — | proved (0.03) | proved (187) | timeout |

## Runtime interpretation

Method discovery time includes the direct EBMC attempt, model calls, compression, and exploratory verifier work. Replay time is reported separately. Published values are historical observations from Amazon EC2 m6i.32xlarge hardware; rIC3 and JasperGold used one-hour limits, while VCFormal includes longer carried-over limits. Tool versions: rIC3 authors’ paper build, JasperGold 2024.09, VCFormal 2024.09. Cross-machine speedups are not claimed.

## Semantic checks

Reset qualification is validated against EBMC 6.0. Complete premise-consistency and antecedent-reachability/vacuity checks remain explicitly unresolved per task.
