#!/usr/bin/env bash
# sotc (Linux): where the GPU threads spend their CPU time, with perf (no signal reaches the game:
# an in-process SIGPROF/real-time-signal sampler ended the process with SIGKILL, cause unknown).
#   bash tools/perf_gpu_threads.sh [seconds] [threads regex]   (the game must be running)
# perf: the distribution's package, or extracted without root into ~/.local/opt/perf (Arch:
# extra/perf + libtraceevent + libpfm, run with LD_LIBRARY_PATH=~/.local/opt/perf/usr/lib).
# kernel.perf_event_paranoid=2 (the default) is enough: user-space samples of your own process.
set -euo pipefail
cd "$(dirname "$0")/.."
seconds=${1:-25}
match=${2:-GpuDraw|GpuComm|GpuReco}
perf=$(command -v perf || true)
if [[ -z $perf && -x $HOME/.local/opt/perf/usr/bin/perf ]]; then
    perf=$HOME/.local/opt/perf/usr/bin/perf
    export LD_LIBRARY_PATH=$HOME/.local/opt/perf/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
fi
[[ -n $perf ]] || { echo 'perf not found (see the header of this script)' >&2; exit 1; }
pid=$(pgrep -f '^(\S*/)?bb-probe ' | head -1 || true)
[[ -n $pid ]] || { echo 'bb-probe is not running' >&2; exit 1; }
tids=$(for t in /proc/"$pid"/task/*; do grep -qE "$match" "$t/comm" && echo -n "${t##*/},"; done)
[[ -n $tids ]] || { echo "no thread of $pid matches $match" >&2; exit 1; }
"$perf" record -q -e cpu-clock:u -F 2000 -t "${tids%,}" -o out/perf-gpu.data -- sleep "$seconds"
"$perf" report -i out/perf-gpu.data --stdio --sort comm,dso --percent-limit 1 2>/dev/null | grep -v '^#' | grep -v '^$'
for comm in $(awk '{print $2}' < <("$perf" report -i out/perf-gpu.data --stdio --sort comm 2>/dev/null | grep -v '^#' | grep -v '^$')); do
    echo "== $comm"
    "$perf" report -i out/perf-gpu.data --stdio --comms "$comm" --sort dso,sym --percent-limit 0.5 2>/dev/null |
        grep -v '^#' | grep -v '^$' | head -25 | cut -c1-160
done
