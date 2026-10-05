# jglib example and smoke test: one lemma DAG, a premise, a counterexample and a cover.
# Run from the directory that contains jasper-utils/ (see jasper-utils/README.md):
#   jasper-utils/bin/jgu run --host HOST --root WORKSPACE --run counter-001 --timeout 600
#       --sync jasper-utils/examples/counter --tcl jasper-utils/examples/counter/run.tcl
source $::env(JGU_LIB)

analyze -sv12 [jgu::script_dir]/counter.sv
elaborate -top counter
clock clk
reset rst
jgu::caps

# Declare every assumption, lemma and target before the first prove.
jgu::dag_init
set k_premise [jgu::rigid k]
jgu::lemma le9 {q <= 4'd9}
assert -name never12 {q != 4'd12}
assert -name k_stable {##1 $stable(k)}
assert -name never5 {q != 4'd5}
cover -name reach9 {q == 4'd9}

jgu::prove_node le9 {} Hp 60
jgu::prove_node never12 {le9} Hp 60
jgu::prove_node k_stable {} Hp 60 k_stable [list $k_premise]
jgu::prove_node never5 {} Ht 60
jgu::prove_node reach9 {} Ht 60

jgu::trace_table never5 {en q} out/never5.tsv
jgu::save_vcd never5 out/never5.vcd
jgu::finish
