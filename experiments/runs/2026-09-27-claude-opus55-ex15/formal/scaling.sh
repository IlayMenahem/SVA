#!/bin/sh
# Record every obligation at each WIDTH given as an argument (e.g. formal/scaling.sh 64 256 1024).
set -u
recorder=../../../accelerate-sva-proofs/scripts/record_run.py
version="JasperGold 2024.06p002 (/tools/cadence2425/JASPER/jasper_2024.06p002/bin/jg on vlsi-luna71)"
for width in "$@"; do
    for obl in x_le_n m_lt_x target; do
        python3 "$recorder" --cwd . --manifest inputs.json --output "proof-runs/$obl-w$width" \
            --timeout 900 --tool-version "$version" \
            -- /bin/sh formal/run_jasper.sh "$obl" "$width" "Hp Ht N B" 600 > "proof-runs/$obl-w$width.rec" 2>&1 &
    done
    wait
done
grep -h "EX15_RESULT\|EX15_COVER" proof-runs/*-w*/stdout.log | grep -v puts
grep -H "^real\|^user" proof-runs/*-w*/stderr.log
