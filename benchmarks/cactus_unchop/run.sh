#!/usr/bin/env bash
set -euo pipefail
MODE="${1:?Usage: run.sh control|v1|v2|v3 input.gfa outdir [threads]}"
INPUT="$(realpath "$2")"
OUT="$3"
THREADS="${4:-32}"
REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
mkdir -p "$(dirname "$OUT")"
mkdir "$OUT"
OUT="$(realpath "$OUT")"
export LC_ALL=C
if [[ "$MODE" == "v3" ]]; then
    export OMP_NUM_THREADS="$THREADS"
else
    export OMP_NUM_THREADS=1
fi
case "$MODE" in
    control) VG="$REPO/bin/vg.control" ;;
    v1|v2|v3) VG="$REPO/bin/vg.experiment" ;;
    *) printf 'Unknown mode: %s\n' "$MODE" >&2; exit 2 ;;
esac
"$VG" version > "$OUT/version.log" 2>&1
case "$MODE" in
    control|v1)
        # The original Cactus command, unchanged.
        COMMAND=(bash -c 'set -eo pipefail; "$1" convert -g -p "$2" | "$1" mod -u -' _ "$VG" "$INPUT")
        ;;
    v2) COMMAND=("$VG" convert -g -p --unchop "$INPUT") ;;
    v3) COMMAND=("$VG" convert -g -p --unchop --unchop-threads "$THREADS" "$INPUT") ;;
esac
printf '%q ' "${COMMAND[@]}" > "$OUT/command.txt"
printf '\n' >> "$OUT/command.txt"
python3 "$REPO/benchmarks/cactus_unchop/monitor.py" "$OUT" \
    /usr/bin/time -v -o "$OUT/time.log" "${COMMAND[@]}"
