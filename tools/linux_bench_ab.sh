#!/usr/bin/env bash
# sotc (Linux): reproducible A/B attract-demo benchmark across Linux tuning presets.
# Runs tools/sotc_play.py headlessly against out/bb-probe and prints a summary table with
# avg FPS (from 45 s on), min FPS, frames >50 ms, worst frame, PC memory state, and memory tracking.
# Usage:
#   bash tools/linux_bench_ab.sh [preset ...]
# Presets:
#   baseline pc_memory pc_memory_3gb pc_memory_preimport pin1 pin2 pin3 no_protect_fast vis_direct
# Environment:
#   SOTC_GAME_DIR   game dump directory (auto-read from user/launcher_settings.json if unset)
#   BENCH_SECONDS   seconds per run (default 90)
#   BENCH_MODES     sotc_modes.py modes (default fps60,af16)
set -euo pipefail
cd "$(dirname "$0")/.."
source tools/bench_common.sh

if [[ -z ${SOTC_GAME_DIR:-} ]] && [[ -f user/launcher_settings.json ]]; then
    SOTC_GAME_DIR=$($PY -c "import json; print(json.load(open('user/launcher_settings.json')).get('game_dir', ''))")
fi
G=${SOTC_GAME_DIR:-"$HOME/Projects/CUSA08809"}
[[ -d "$G" ]] || { echo "Game dir not found: $G (set SOTC_GAME_DIR)" >&2; exit 1; }

SECONDS_TOTAL=${BENCH_SECONDS:-90}
MODES=${BENCH_MODES:-fps60,af16}

$PY scripts/sotc_modes.py "$G" --out out --modes "$MODES" --cvars "$BENCH_CVARS" >/dev/null
cp out/patches.bin out/bench.patches
cp out/cmdline.bin out/bench.cmdline
bench_env "$MODES"

if (($# > 0)); then
    PRESETS=("$@")
else
    PRESETS=(baseline pc_memory_3gb pin2 pin3 no_protect_fast)
fi

preset_env() {
    case "$1" in
        baseline)
            echo "" ;;
        pc_memory)
            echo "SOTC_PC_MEMORY=1 SOTC_TEX_DIRECT=1 SOTC_TEX_GATHER=1" ;;
        pc_memory_3gb)
            echo "SOTC_PC_MEMORY=1 SOTC_PC_MEMORY_MAX_MB=3072 SOTC_TEX_DIRECT=1 SOTC_TEX_GATHER=1" ;;
        pc_memory_preimport)
            echo "SOTC_PC_MEMORY=1 SOTC_PC_MEMORY_PREIMPORT=1 SOTC_TEX_DIRECT=1 SOTC_TEX_GATHER=1" ;;
        pin1)
            echo "SOTC_PIN=1" ;;
        pin2)
            echo "SOTC_PIN=2" ;;
        pin3)
            echo "SOTC_PIN=3" ;;
        no_protect_fast)
            echo "SOTC_PROTECT_FAST=0" ;;
        vis_direct)
            echo "SOTC_PC_MEMORY=1 SOTC_VIS_DIRECT=1 SOTC_VIS_DIRECT_ORDER=1" ;;
        *)
            echo "Unknown preset: $1" >&2; return 1 ;;
    esac
}

echo "Linux A/B attract benchmark: game=$G duration=${SECONDS_TOTAL}s modes=$MODES"
printf '%-20s | %-8s | %-7s | %-9s | %-8s | %-12s | %s\n' \
    "Preset" "Avg FPS" "Min FPS" ">50ms f" "Worst ms" "Tracker" "Notes"
printf '%-20s-+-%-8s-+-%-7s-+-%-9s-+-%-8s-+-%-12s-+-%s\n' \
    "--------------------" "--------" "-------" "---------" "--------" "------------" "--------------------"

for preset in "${PRESETS[@]}"; do
    extra_str=$(preset_env "$preset")
    extra_args=()
    for kv in $extra_str; do
        extra_args+=(--env "$kv")
    done
    log="out/bench_${preset}.log"
    rm -f "$log"
    SOTC_GAME_DIR="$G" timeout $((SECONDS_TOTAL + 120)) $PY tools/sotc_play.py "$SECONDS_TOTAL" \
        --log "$log" --patches out/bench.patches --cmdline out/bench.cmdline \
        --env BB_VBLANK_HZ=120 --env SOTC_FPS=1 "${BENCH_ENV[@]}" "${extra_args[@]}" >/dev/null 2>&1 || true

    stats=$($PY - "$log" <<'PYEOF'
import re, sys
text = open(sys.argv[1], errors='replace').read()
fps_samples = []
for m in re.finditer(r'SOTC FPS[^0-9]*([0-9.]+)\s+@\s*([0-9.]+)', text):
    f, t = float(m.group(1)), float(m.group(2))
    if t >= 45.0:
        fps_samples.append(f)
if not fps_samples:
    for m in re.finditer(r'SOTC FPS.*?([0-9]+(?:\.[0-9]+)?)\s*(?:\(|at)?', text):
        fps_samples.append(float(m.group(1)))
avg_fps = f"{sum(fps_samples)/len(fps_samples):.2f}" if fps_samples else "n/a"
min_fps = f"{min(fps_samples):.1f}" if fps_samples else "n/a"
over50 = 0
worst = 0.0
for m in re.finditer(r'(\d+)\s+quadros acima de 50 ms,\s+pior\s+([0-9.]+)\s+ms|(\d+)\s+frames over 50 ms,\s+worst\s+([0-9.]+)\s+ms', text):
    if m.group(1):
        over50 += int(m.group(1)); worst = max(worst, float(m.group(2)))
    else:
        over50 += int(m.group(3)); worst = max(worst, float(m.group(4)))
tracker = "userfaultfd" if "Memory tracking method: userfaultfd" in text else ("signals" if "Memory tracking method: signals" in text else "unknown")
notes = []
if "SOTC PC memory:" in text:
    m_pc = re.search(r'SOTC PC memory: ([^\n]+)', text)
    if m_pc:
        notes.append(m_pc.group(1)[:48])
if "Runtime: thread placement" in text:
    m_pin = re.search(r'Runtime: thread placement[^\n]+', text)
    if m_pin:
        notes.append(m_pin.group(0)[:48])
worst_s = f"{worst:.1f}" if worst else "n/a"
print(f"{avg_fps}|{min_fps}|{over50}|{worst_s}|{tracker}|{'; '.join(notes)}")
PYEOF
)
    IFS='|' read -r avg_fps min_fps over50 worst_ms tracker notes <<< "$stats"
    printf '%-20s | %-8s | %-7s | %-9s | %-8s | %-12s | %s\n' \
        "$preset" "$avg_fps" "$min_fps" "$over50" "$worst_ms" "$tracker" "$notes"
done
