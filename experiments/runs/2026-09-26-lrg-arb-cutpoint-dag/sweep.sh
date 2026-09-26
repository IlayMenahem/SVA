#!/bin/sh
# Development sweep: for each N, run the DAG levels (and optional extra levels, e.g. X1 X3 B) on vlsi.
# Usage: sh sweep.sh "<N list>" [extra levels...]
set -e
ns=$1; shift
extra="$*"
for n in $ns; do
  python3 gen.py "$n"
  remote="sva/opus_cpdag2/N$n"
  levels="$(cat "work/N$n/dag_levels.txt") $extra"
  ssh vlsi "rm -rf $remote && mkdir -p $remote"
  COPYFILE_DISABLE=1 tar czf - --no-xattrs -C "work/N$n" $levels -C ../.. run_levels.sh \
    | ssh vlsi "cd $remote && tar xzf -"
  echo "== N$n"
  ssh vlsi "env JOBS=${JOBS:-6} sh $remote/run_levels.sh $remote $levels"
done
