#!/usr/bin/env bash
set -euo pipefail
RESULTS="$(realpath "${1:?Usage: verify.sh results_directory [threads] [mode ...]}")"
THREADS="${2:-4}"
MODES=("${@:3}")
if [[ ${#MODES[@]} == 0 ]]; then MODES=(control v1 v2 v3); fi
REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
VG="${VG_VERIFY:-$REPO/bin/vg.experiment}"
VG="$(realpath "$VG")"
export LD_LIBRARY_PATH="$(dirname "$VG")/../lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export OMP_NUM_THREADS="$THREADS" LC_ALL=C
for MODE in "${MODES[@]}"; do
    python3 -c 'import json,sys; s=json.load(open(sys.argv[1])); assert s["exit_code"]==0, "run failed"' \
        "$RESULTS/$MODE/summary.json"
    /usr/bin/time -v -o "$RESULTS/$MODE/verify.time.log" \
        "$VG" unchop-fingerprint --threads "$THREADS" "$RESULTS/$MODE/result.vg" \
        > "$RESULTS/$MODE/fingerprint.json" 2> "$RESULTS/$MODE/verify.log"
done
python3 "$REPO/benchmarks/cactus_unchop/compare.py" "$RESULTS" "${MODES[@]}"
