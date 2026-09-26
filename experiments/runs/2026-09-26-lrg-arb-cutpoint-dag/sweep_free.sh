#!/bin/sh
# DAG sweep for VARIANT=free|nlogn (default free): for each N, run gen_$VARIANT.py levels (and optional extra levels, e.g. X1 X3) on vlsi.
# Usage: sh sweep_free.sh "<N list>" [extra levels...]
set -e
ns=$1; shift
extra="$*"
for n in $ns; do
  python3 gen_${VARIANT:-free}.py "$n"
  remote="sva/opus_cpdag_${VARIANT:-free}/N$n"
  levels="$(cat "work/${VARIANT:-free}/N$n/dag_levels.txt") $extra"
  ssh vlsi "rm -rf $remote && mkdir -p $remote"
  COPYFILE_DISABLE=1 tar czf - --no-xattrs -C "work/${VARIANT:-free}/N$n" $levels -C ../../.. run_levels.sh \
    | ssh vlsi "cd $remote && tar xzf -"
  echo "== N$n"
  ssh vlsi "env JOBS=${JOBS:-6} sh $remote/run_levels.sh $remote $levels"
done
