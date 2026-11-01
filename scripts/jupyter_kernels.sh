#!/usr/bin/env bash
# List the Jupyter kernels running on this machine, and stop the ones no longer wanted.
#
# An editor holds one kernel per open notebook and keeps it after the tab loses focus, so
# kernels accumulate across a session. Each carries its interpreter, its imported modules and
# whatever the notebook left in memory, and a kernel that imported a GPU framework also holds a
# CUDA context until the process exits.
#
# Selection acts only on processes whose command line carries `ipykernel_launcher`, so nothing
# else on the machine is reachable from here. A stop sends SIGTERM, waits `GRACE`, then sends
# SIGKILL to whatever remains.
#
# BUSY is decided by CPU share: a kernel above `BUSY_CPU` per cent is running a cell, and the
# default skips it. `--all` includes it.
#
# A kernel reads 0 per cent between two cells of a run that is still going, so CPU share alone
# admits a kernel another process is using. Anything younger than `MIN_AGE` is therefore held
# back as well, which covers a script or an agent mid-notebook. `--all` and `--pid` override it.
#
# Usage:
#   scripts/jupyter_kernels.sh                  list every kernel
#   scripts/jupyter_kernels.sh --stop           stop the idle ones
#   scripts/jupyter_kernels.sh --stop --all     stop every one, busy included
#   scripts/jupyter_kernels.sh --stop --older-than 60    only those older than 60 minutes
#   scripts/jupyter_kernels.sh --stop --pid 1021232      one named kernel
#   scripts/jupyter_kernels.sh --stop --parent code      only those a named parent started
set -u

GRACE=${GRACE:-5}          # seconds between SIGTERM and SIGKILL
BUSY_CPU=${BUSY_CPU:-5.0}  # per cent CPU above which a kernel counts as running a cell
MIN_AGE=${MIN_AGE:-120}    # seconds; a kernel younger than this is in use by something

stop=0; all=0; older=0; want_pid=""; want_parent=""
while [ $# -gt 0 ]; do
  case "$1" in
    --stop)        stop=1 ;;
    --all)         all=1 ;;
    --older-than)  older=${2:?minutes}; shift ;;
    --pid)         want_pid=${2:?pid}; shift ;;
    --parent)      want_parent=${2:?name}; shift ;;
    -h|--help)     sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)             echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

# GPU memory per pid, summed across cards, so a kernel holding CUDA contexts on several
# devices reports one number. Non-numeric fields (N/A under some driver modes) are skipped.
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

if [ "$count" = "0" ]; then echo "no kernels match"; exit 0; fi
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
