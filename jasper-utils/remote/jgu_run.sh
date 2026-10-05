#!/bin/sh
# One Jasper session per run directory; uploaded by `jgu run` as <run>/.jgu/jgu_run.sh.
#
#   sh <run>/.jgu/jgu_run.sh start [--detach]   run jg (in the background with --detach)
#   sh <run>/.jgu/jgu_run.sh status             print one JGU_STATUS line
#   sh <run>/.jgu/jgu_run.sh kill               stop the run, keeping its time record
#   sh <run>/.jgu/jgu_run.sh pack               tar the run outputs to stdout
#   sh -s list <root> < jgu_run.sh              one JGU_STATUS line per run under <root>/runs
#
# Parameters come from <run>/.jgu/params.sh. Engines run under
# `/usr/bin/time timeout jg`: a TERM sent to `timeout` reaches the whole jg process
# group, and `time` still writes time.txt after jg exits.
set -u

TIME_FORMAT='JGU_TIME wall=%e user=%U sys=%S maxrss_kb=%M'
OUTPUTS='jg.log time.txt exit_code results.json cpu_sample.txt out .jgu/params.sh .jgu/inputs.sha256'

absolute_root() {
    case $1 in
        /*) printf '%s\n' "$1" ;;
        *) printf '%s\n' "$HOME/$1" ;;
    esac
}

hash_inputs() {
    find . \( -path ./.jgu -o -path ./jgproj \) -prune -o -type f -exec sha256sum {} + \
        | LC_ALL=C sort -k 2 > .jgu/inputs.sha256
}

start_sampler() {
    session=$(ps -o sid= -p $$ | tr -d ' ')
    python3 .jgu/cpu_sampler.py "$session" $$ "$JGU_SAMPLE_PERIOD_S" cpu_sample.txt \
        < /dev/null > .jgu/sampler.log 2>&1 &
}

start() {
    . .jgu/params.sh
    JGU_ROOT=$(absolute_root "$JGU_ROOT")
    JGU_RUN_DIR=$(pwd)
    JGU_LIB=$JGU_RUN_DIR/.jgu/jglib.tcl
    export JGU_ROOT JGU_RUN_DIR JGU_LIB
    date +%s > .jgu/started
    ps -o pgid= -p $$ | tr -d ' ' > .jgu/pgid
    hash_inputs
    mkdir -p out
    if [ "$JGU_SAMPLE_CPU" = 1 ]; then
        start_sampler
    fi
    /usr/bin/time -o time.txt -f "$TIME_FORMAT" \
        timeout -k "$JGU_KILL_AFTER_S" "$JGU_TIMEOUT_S" \
        "$JGU_JG" -batch -proj jgproj -tcl "$JGU_TCL" < /dev/null > jg.log 2>&1 &
    echo $! > .jgu/time.pid
    wait $!
    code=$?
    echo "$code" > exit_code
    date +%s > .jgu/finished
    : > .jgu/done
    return "$code"
}

detach() {
    setsid sh "$1" start < /dev/null > .jgu/detach.log 2>&1 &
    echo "JGU_STATUS run=$(basename "$PWD") state=started"
}

state() {
    if [ -f .jgu/done ]; then
        echo done
    elif [ ! -f .jgu/pgid ]; then
        echo new
    elif pgrep -g "$(cat .jgu/pgid)" > /dev/null 2>&1; then
        echo running
    else
        echo lost
    fi
}

elapsed() {
    if [ ! -f .jgu/started ]; then
        echo -
    elif [ -f .jgu/finished ]; then
        echo $(( $(cat .jgu/finished) - $(cat .jgu/started) ))
    else
        echo $(( $(date +%s) - $(cat .jgu/started) ))
    fi
}

status() {
    times=$(sed -n 's/^JGU_TIME //p' time.txt 2>/dev/null | tail -n 1)
    sampled=$(sed -n 's/.*total_cpu_s=\([0-9.]*\).*/\1/p' cpu_sample.txt 2>/dev/null | tail -n 1)
    killed=no
    [ -f .jgu/killed ] && killed=yes
    printf 'JGU_STATUS run=%s state=%s exit=%s killed=%s elapsed_s=%s sampled_cpu_s=%s %s\n' \
        "$(basename "$PWD")" "$(state)" "$(cat exit_code 2>/dev/null || echo -)" "$killed" \
        "$(elapsed)" "${sampled:--}" "$times"
}

kill_run() {
    if [ -f .jgu/done ] || [ ! -f .jgu/time.pid ]; then
        status
        return 0
    fi
    . .jgu/params.sh
    : > .jgu/killed
    time_pid=$(cat .jgu/time.pid)
    timeout_pid=$(pgrep -P "$time_pid" | head -n 1)
    [ -n "$timeout_pid" ] && kill -s TERM "$timeout_pid" 2> /dev/null
    waited=0
    while [ ! -f .jgu/done ] && [ "$waited" -lt $(( JGU_KILL_AFTER_S + 10 )) ]; do
        sleep 1
        waited=$(( waited + 1 ))
    done
    if [ ! -f .jgu/done ]; then
        for group in $timeout_pid $(cat .jgu/pgid); do
            kill -s KILL -- "-$group" 2> /dev/null
        done
    fi
    status
}

pack() {
    present=
    for name in $OUTPUTS; do
        [ -e "$name" ] && present="$present $name"
    done
    if [ -z "$present" ]; then
        echo "jgu: no outputs in $PWD" >&2
        return 1
    fi
    tar -cf - $present
}

list_runs() {
    runs=$(absolute_root "$1")/runs
    [ -d "$runs" ] || return 0
    for dir in "$runs"/*/; do
        [ -d "$dir/.jgu" ] && (cd "$dir" && status)
    done
    return 0
}

mode=${1:-}
case $mode in
    list)
        list_runs "${2:?usage: sh -s list <root>}"
        ;;
    start|status|kill|pack)
        script=$(cd "$(dirname "$0")" && pwd)/$(basename "$0")
        cd "$(dirname "$script")/.." || exit 2
        case $mode in
            start)
                if [ "${2:-}" = --detach ]; then detach "$script"; else start; fi
                ;;
            status) status ;;
            kill) kill_run ;;
            pack) pack ;;
        esac
        ;;
    *)
        echo "usage: jgu_run.sh start [--detach] | status | kill | pack | list <root>" >&2
        exit 2
        ;;
esac
