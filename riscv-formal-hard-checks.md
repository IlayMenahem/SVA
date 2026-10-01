# Hardest riscv-formal Checks

## Properties

1. `insn_mul*`, `insn_div*`, `insn_rem*`
2. `liveness`
3. `reg`
4. `causal`, `causal_mem`, `causal_io`
5. `pc_fwd`, `pc_bwd`
6. `csrw`, `csrc_any`, `csrc_hpm`, `csrc_inc`, `csrc_zero`, `csrc_upcnt`
7. `unique`
8. `bus_imem`, `bus_dmem`, `bus_imem_fault`, `bus_dmem_fault`
9. `complete`, `ill`

## Cores

Cores to check the properties on.
1. NERV (single cycle) 
2. Ibex
3. CVA6 (OOO + Branch prediction + Caches)
