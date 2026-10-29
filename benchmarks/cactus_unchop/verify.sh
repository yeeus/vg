#!/usr/bin/env bash
set -euo pipefail
RESULTS="$(realpath "${1:?Usage: verify.sh results_directory}")"
REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
export OMP_NUM_THREADS=1 LC_ALL=C
for MODE in control v1 v2 v3; do
    python3 -c 'import json,sys; s=json.load(open(sys.argv[1])); assert s["exit_code"]==0, "run failed"' \
        "$RESULTS/$MODE/summary.json"
    /usr/bin/time -v -o "$RESULTS/$MODE/verify.time.log" \
        "$REPO/bin/vg.experiment" unchop-fingerprint "$RESULTS/$MODE/result.vg" \
        > "$RESULTS/$MODE/fingerprint.json" 2> "$RESULTS/$MODE/verify.log"
done
python3 "$REPO/benchmarks/cactus_unchop/compare.py" "$RESULTS"
