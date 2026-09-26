#!/bin/sh
# Clean replay of the proof DAG for lrg_arb_lrg_N on host vlsi.
# Usage: sh replay.sh N   (from this directory)
set -e
n=$1
remote="sva/opus_cpdag_replay/N$n"
python3 gen.py "$n"
ssh vlsi "rm -rf $remote && mkdir -p $remote"
COPYFILE_DISABLE=1 tar czf - --no-xattrs -C "work/N$n" dag_levels.txt $(cat "work/N$n/dag_levels.txt") X1 X3 \
  -C ../.. run_levels.sh replay_remote.sh \
  | ssh vlsi "cd $remote && tar xzf -"
ssh vlsi "sh $remote/replay_remote.sh"
