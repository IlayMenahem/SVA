# Global versus tracked-pair arbiter proof

EBMC 6.0 / MiniSAT, k=4, 60 seconds per obligation; sequential calls. Times below are recorder wall seconds, including startup/cleanup. Each completed reusable total includes preservation, invariant, and target. Nonvacuity diagnostics and discovery costs are excluded from reusable totals.

| N | Global replay (s) | Pair replay (s) | Global / pair |
|---:|---:|---:|---:|
| 4 | 0.160 | 0.158 | 1.01x |
| 8 | 0.611 | 0.391 | 1.56x |
| 16 | 15.783 | 1.967 | 8.02x |
| 32 | timeout | 11.418 | — |
| 64 | tool_error (exit -11) | 95.511 | — |

## Per-obligation measurements

| N | Phase | Obligation | Status | Wall (s) | CPU incl. recorder (s) |
|---:|---|---|---|---:|---:|
| 4 | discovery | preservation | proved | 0.07788958300079685 | 0.098 |
| 4 | discovery | global-invariant | proved | 0.04075237500364892 | 0.068 |
| 4 | discovery | global-target | proved | 0.04074462500284426 | 0.074 |
| 4 | discovery | pair-invariant | proved | 0.039129292003053706 | 0.070 |
| 4 | discovery | pair-target | proved | 0.04112612500466639 | 0.071 |
| 4 | discovery | global-reach | witness | 0.020976917003281415 | 0.061 |
| 4 | discovery | pair-reach | witness | 0.020685790994320996 | 0.060 |
| 4 | replay | preservation | proved | 0.07767850000527687 | 0.098 |
| 4 | replay | global-invariant | proved | 0.041209333001461346 | 0.070 |
| 4 | replay | global-target | proved | 0.04083637499570614 | 0.072 |
| 4 | replay | pair-invariant | proved | 0.03951904099812964 | 0.072 |
| 4 | replay | pair-target | proved | 0.04083195799466921 | 0.073 |
| 8 | discovery | preservation | proved | 0.24266829200496431 | 0.250 |
| 8 | discovery | global-invariant | proved | 0.23984979200031376 | 0.257 |
| 8 | discovery | global-target | proved | 0.131394291005563 | 0.136 |
| 8 | discovery | pair-invariant | proved | 0.07800420800049324 | 0.117 |
| 8 | discovery | pair-target | proved | 0.07662158299353905 | 0.118 |
| 8 | discovery | global-reach | witness | 0.040222667004854884 | 0.079 |
| 8 | discovery | pair-reach | witness | 0.038785708995419554 | 0.074 |
| 8 | replay | preservation | proved | 0.23816320799960522 | 0.249 |
| 8 | replay | global-invariant | proved | 0.2406059999993886 | 0.257 |
| 8 | replay | global-target | proved | 0.13203545800206484 | 0.135 |
| 8 | replay | pair-invariant | proved | 0.07786037500045495 | 0.118 |
| 8 | replay | pair-target | proved | 0.07542874999489868 | 0.118 |
| 16 | discovery | preservation | proved | 1.1505955419997917 | 1.139 |
| 16 | discovery | global-invariant | proved | 14.205162042002485 | 14.178 |
| 16 | discovery | global-target | proved | 0.4000504169962369 | 0.411 |
| 16 | discovery | pair-invariant | proved | 0.39760829199803993 | 0.429 |
| 16 | discovery | pair-target | proved | 0.4063967500042054 | 0.419 |
| 16 | discovery | global-reach | witness | 0.1306492080038879 | 0.159 |
| 16 | discovery | pair-reach | witness | 0.129252708000422 | 0.139 |
| 16 | replay | preservation | proved | 1.161357125005452 | 1.155 |
| 16 | replay | global-invariant | proved | 14.218712666995998 | 14.199 |
| 16 | replay | global-target | proved | 0.4031613749975804 | 0.413 |
| 16 | replay | pair-invariant | proved | 0.4027315420025843 | 0.424 |
| 16 | replay | pair-target | proved | 0.40280966699356213 | 0.424 |
| 32 | discovery | preservation | proved | 6.565934625003138 | 6.557 |
| 32 | discovery | global-invariant | timeout | 60.01338754199969 | 59.918 |
| 32 | discovery | global-target | proved | 2.5204521250052494 | 2.552 |
| 32 | discovery | pair-invariant | proved | 2.842896957998164 | 2.851 |
| 32 | discovery | pair-target | proved | 2.0544806249963585 | 2.068 |
| 32 | discovery | global-reach | witness | 0.5127171249987441 | 0.545 |
| 32 | discovery | pair-reach | witness | 0.4045263750012964 | 0.419 |
| 32 | replay | preservation | proved | 6.608038750004198 | 6.594 |
| 32 | replay | pair-invariant | proved | 2.788601500004006 | 2.825 |
| 32 | replay | pair-target | proved | 2.0210314159994596 | 2.046 |
| 64 | discovery | preservation | proved | 45.84669691700401 | 45.814 |
| 64 | discovery | global-invariant | tool_error (exit -11) | 0.07456208299845457 | 0.088 |
| 64 | discovery | pair-invariant | proved | 38.111066750003374 | 38.023 |
| 64 | discovery | pair-target | proved | 10.630397499997343 | 10.633 |
| 64 | discovery | pair-reach | witness | 1.7478169580062968 | 1.787 |
| 64 | replay | preservation | proved | 46.21136950000073 | 46.104 |
| 64 | replay | pair-invariant | proved | 38.43431604200305 | 38.349 |
| 64 | replay | pair-target | proved | 10.8654568330021 | 10.831 |

Total recorded verifier wall time: 313.795 s across 54 calls. Shared preservation calls are counted once in this experimental total, but in full for each strategy's reusable total.

One discovery and one clean replay per completed strategy/size; small timing differences are not statistically established. A timeout is censored and does not show that the property is false. A proved target with an unresolved helper is conditional and not a completed proof. See SEMANTICS.md for reset, preservation, selection, and trust boundaries.

Replay the full comparison from the repository root with a fresh output directory:

```sh
lean-ctx -c 'python3 experiments/pi-headroom-sva/scaling_compare.py --root experiments/pi-headroom-sva/runs/scaling-global-pair-repeat'
```

This is a direct local proof-strategy experiment, not a new Astra agent run. No model API requests were issued for the verifier sweep; this conversation's model cost is unavailable.
