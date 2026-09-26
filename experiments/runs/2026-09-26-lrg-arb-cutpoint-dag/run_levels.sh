#!/bin/sh
# Usage (on vlsi): sh run_levels.sh <work/N dir> [levels...]
# Runs each level's Jasper session, at most $JOBS concurrently; prints per-property results and wall time.
JG=/tools/cadence2425/JASPER/jasper_2024.06p002/bin/jg
JOBS=${JOBS:-6}
dir=$(cd "$1" && pwd); shift
levels=${*:-$(cat "$dir/dag_levels.txt")}
export JG dir
start=$(date +%s.%N)
printf '%s\n' $levels | xargs -P "$JOBS" -I{} sh -c \
  'cd "$dir/{}" && rm -rf jgproject summary.txt && /usr/bin/time -f "WALL {} %e s CPU %U+%S" "$JG" -batch -tcl run.tcl > log.txt 2> time.txt'
end=$(date +%s.%N)
for l in $levels; do
  grep WALL "$dir/$l/time.txt"
  grep -E "^RESULT " "$dir/$l/log.txt" | grep -v " unprocessed$" | awk '{print $3}' | sort | uniq -c | sed "s/^/  $l /"
  grep -E "^RESULT " "$dir/$l/log.txt" | grep -v -E " (proven|covered)$" | grep -v " unprocessed$" | head -5
  grep -E "ERROR" "$dir/$l/log.txt" | head -5
done
echo "TOTAL_WALL $(echo "$end - $start" | bc)"
