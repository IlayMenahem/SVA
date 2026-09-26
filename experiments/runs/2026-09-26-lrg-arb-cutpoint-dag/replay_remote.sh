#!/bin/sh
# Remote half of replay.sh: run all DAG levels and negative controls X1 X3 (expected cex), then dump every property result and Jasper version.
cd "$(dirname "$0")"
levels="$(cat dag_levels.txt) X1 X3"
sh ./run_levels.sh . $levels
for l in $levels; do
  echo "== $l"
  grep -m1 -E "Jasper.*(Version|version|2024)" "$l/log.txt"
  grep -E "^RESULT " "$l/log.txt"
done
