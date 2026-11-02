#!/usr/bin/env bash
# jupyter kernels: list or stop started kernels.
#   jupyter notebook starts kernel per notebook. Zombie kernels accumulate interpreter, modules, memory and CUDA.
#
# jupyter kernels --help
#   jupyter kernels         # list every kernel
#   jupyter kernels --stop  # stop idle kernels SIGTERM, wait GRACE [5s], then SIGKILL
#                           # idle: (CPU Usage < BUSY_CPU [5%] & age > MIN_AGE [120s])
#   jupyter kernels --stop --all               # all kernels, including BUSY and MIN_AGE
#   jupyter kernels --stop --older-than <int>  # only older than <int> minutes
#   jupyter kernels --stop --pid <int>         # only kernel with PID
#   jupyter kernels --stop --parent <str>      # only kernels started by parent <str>
set -u

GRACE=${GRACE:-5}          # seconds; grace period between SIGTERM and SIGKILL.
BUSY_CPU=${BUSY_CPU:-5.0}  # %; a kernel memory > CPU % is considered running.
MIN_AGE=${MIN_AGE:-120}    # seconds; a kernel started < MIN_AGE is most likely in use.

stop=0; all=0; older=0; want_pid=""; want_parent=""
while [ $# -gt 0 ]; do
  case "$1" in
    --stop)        stop=1 ;;
    --all)         all=1 ;;
    --older-than)  older=${2:?minutes}; shift ;;
    --pid)         want_pid=${2:?pid}; shift ;;
    --parent)      want_parent=${2:?name}; shift ;;
    -h|--help)     sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)             echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

# GPU memory per pid, summed across cards. Excludes if non-numeric (N/A)
gpu_of() {
  nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits 2>/dev/null |
    awk -F' *, *' -v p="$1" '$1 == p && $2 ~ /^[0-9]+$/ { s += $2 } END { print s + 0 }'
}

kernels() {
  pgrep -f ipykernel_launcher 2>/dev/null || true
}

selected=""
total_rss=0; total_gpu=0; count=0
printf "%8s %10s %8s %8s %7s %9s  %s\n" "pid" "parent" "age" "rss MB" "cpu%" "gpu MiB" "working directory"
for pid in $(kernels); do
    [ -n "$want_pid" ] && [ "$pid" != "$want_pid" ] && continue
    ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ') || continue
    [ -z "$ppid" ] && continue
    pname=$(ps -o comm= -p "$ppid" 2>/dev/null || echo "-")
    [ -n "$want_parent" ] && [ "$pname" != "$want_parent" ] && continue
    secs=$(ps -o etimes= -p "$pid" | tr -d ' ')
    [ "$older" -gt 0 ] && [ "$secs" -lt $((older * 60)) ] && continue
    rss=$(( $(ps -o rss= -p "$pid" | tr -d ' ') / 1024 ))
    cpu=$(ps -o %cpu= -p "$pid" | tr -d ' ')
    gpu=$(gpu_of "$pid")
    cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || echo "-")
    busy=$(awk -v c="$cpu" -v b="$BUSY_CPU" 'BEGIN { print (c > b) ? 1 : 0 }')
    young=0
    [ "$secs" -lt "$MIN_AGE" ] && young=1
    mark=""
    [ "$busy" = "1" ] && mark=" running a cell"
    [ "$young" = "1" ] && mark="$mark held, under ${MIN_AGE}s old"
    printf "%8s %10s %5dm%02ds %8s %7s %9s  %s%s\n" \
        "$pid" "$pname" $((secs / 60)) $((secs % 60)) "$rss" "$cpu" "$gpu" "$cwd" "$mark"
    count=$((count + 1))
    total_rss=$((total_rss + rss)); total_gpu=$((total_gpu + gpu))
    keep_back=0
    [ "$busy" = "1" ] && keep_back=1
    [ "$young" = "1" ] && keep_back=1
    if [ "$keep_back" = "0" ] || [ "$all" = "1" ] || [ -n "$want_pid" ]; then
        selected="$selected $pid"
    fi
done

if [ "$count" = "0" ]; then
    echo "No live kernels match args";
    sed -n '4,12p' "$0" | sed 's/^# \{0,1\}//';
    exit 0;
fi
echo
echo "$count kernels holding ${total_rss} MB of host memory and ${total_gpu} MiB of device memory"

if [ "$stop" = "0" ]; then
    n=$(echo $selected | wc -w)
    echo "$n would stop. Add --stop to act, --all to include one that is busy or newly started."
    exit 0
fi

[ -z "$selected" ] && { echo "nothing to stop"; exit 0; }
echo "stopping:$selected"
# shellcheck disable=SC2086
kill -TERM $selected 2>/dev/null
sleep "$GRACE"
left=""
for pid in $selected; do kill -0 "$pid" 2>/dev/null && left="$left $pid"; done
if [ -n "$left" ]; then
    echo "still alive after ${GRACE}s, sending SIGKILL:$left"
    # shellcheck disable=SC2086
    kill -KILL $left 2>/dev/null
fi
sleep 1
remaining=$(kernels | wc -l)
echo "done. $remaining kernels remain on the machine"
