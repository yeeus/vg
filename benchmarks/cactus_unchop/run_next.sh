#!/usr/bin/env bash
set -euo pipefail
MODE="${1:?Usage: run_next.sh mode input outdir vg_binary [threads]}"
INPUT="$(realpath "$2")"
OUT="$3"
VG="$(realpath "$4")"
VG_PREFIX="$(dirname "$(dirname "$VG")")"
THREADS="${5:-4}"
REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
case "$THREADS" in ''|*[!0-9]*) printf 'threads must be a positive integer\n' >&2; exit 2;; esac
if (( THREADS < 1 )); then exit 2; fi
case "$MODE" in control|v2|v4|v5|v6|v7|xg-control|xg-stream|xg-compact|full-control|full-next|clip-control|clip-fused|filter-control|filter-fused) ;;
    *) printf 'Unknown mode: %s\n' "$MODE" >&2; exit 2;; esac
mkdir -p "$(dirname "$OUT")"
mkdir "$OUT"
OUT="$(realpath "$OUT")"
export LC_ALL=C
export LD_LIBRARY_PATH="$VG_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
unset VG_BENCH_NUMERIC_IDS VG_BENCH_FAST_SERIALIZE VG_BENCH_PATH_THREADS VG_BENCH_XG_MODE
export VG_BENCH_PHASES=1 OMP_NUM_THREADS=1
OUTPUT=result.vg
case "$MODE" in
    control) COMMAND=(bash -c 'set -eo pipefail; "$1" convert -g -p "$2" | "$1" mod -u -' _ "$VG" "$INPUT");;
    v2|v4|v5|v6|v7)
        COMMAND=("$VG" convert -g -p --unchop)
        if [[ "$MODE" != v2 ]]; then export VG_BENCH_NUMERIC_IDS=1; fi
        if [[ "$MODE" == v5 || "$MODE" == v6 || "$MODE" == v7 ]]; then export VG_BENCH_FAST_SERIALIZE=1; fi
        if [[ "$MODE" == v6 || "$MODE" == v7 ]]; then
            export VG_BENCH_PATH_THREADS="$THREADS" OMP_NUM_THREADS="$THREADS"
        fi
        if [[ "$MODE" == v7 ]]; then COMMAND+=(--unchop-threads "$THREADS"); fi
        COMMAND+=("$INPUT")
        ;;
    xg-*)
        export OMP_NUM_THREADS="$THREADS"
        if [[ "$MODE" == xg-stream ]]; then export VG_BENCH_XG_MODE=stream; fi
        if [[ "$MODE" == xg-compact ]]; then export VG_BENCH_XG_MODE=compact; fi
        COMMAND=("$VG" convert -x "$INPUT" -t "$THREADS")
        OUTPUT=result.xg
        ;;
    full-control|full-next)
        CLIP_VG="$(command -v clip-vg)"
        if [[ "$MODE" == full-next ]]; then
            export VG_BENCH_FAST_SERIALIZE=1 VG_BENCH_PATH_THREADS="$THREADS" OMP_NUM_THREADS="$THREADS"
        fi
        COMMAND=(bash -c 'set -eo pipefail; "$1" "$3" -f -e GRCh38 -d _MINIGRAPH_ -L -F | "$2" mod -X 1024 - | "$2" paths -x - -n -Q GRCh38 -t 1 | "$2" clip -d 1 - -P GRCh38 | "$2" ids -s -' _ "$CLIP_VG" "$VG" "$INPUT")
        ;;
    clip-control|clip-fused)
        CLIP_VG="$(command -v clip-vg)"
        if [[ "$MODE" == clip-control ]]; then
            COMMAND=(bash -c 'set -eo pipefail; "$1" "$3" -f -e GRCh38 -d _MINIGRAPH_ -u 10000 -a _MINIGRAPH_ -I 100000 -k 50000 -T -1.0 | "$2" clip -d 1 - -P GRCh38 | "$2" clip -sS - -P GRCh38 | "$2" clip - -D 10000000 -P GRCh38 -c 1000 -m 1000' _ "$CLIP_VG" "$VG" "$INPUT")
        else
            COMMAND=(bash -c 'set -eo pipefail; "$1" "$3" -f -e GRCh38 -d _MINIGRAPH_ -u 10000 -a _MINIGRAPH_ -I 100000 -k 50000 -T -1.0 | "$2" clip --cactus-clip - -D 10000000 -P GRCh38 -c 1000 -m 1000' _ "$CLIP_VG" "$VG" "$INPUT")
        fi
        ;;
    filter-control)
        COMMAND=(bash -c 'set -eo pipefail; "$1" clip "$2" -d 132 -P GRCh38 -P CHM13v2 -P CN1v1 -m 1000 | "$1" clip -d 1 - -P GRCh38 -P CHM13v2 -P CN1v1 | "$1" clip -sS - -P GRCh38' _ "$VG" "$INPUT")
        ;;
    filter-fused)
        COMMAND=("$VG" clip --cactus-filter "$INPUT" -d 132 -P GRCh38 -P CHM13v2 -P CN1v1 -m 1000)
        ;;
esac
"$VG" version > "$OUT/version.log" 2>&1
ldd "$VG" > "$OUT/libraries.log" 2>&1 || true
case "$MODE" in control|full-control|clip-control|filter-control)
    if ! grep -q '^vg version .*gf2ed0bbd4' "$OUT/version.log"; then
        printf 'Control modes require original vg f2ed0bbd4\n' >&2; exit 2
    fi
    if grep -q 'libhandlegraph.so' "$OUT/libraries.log"; then
        if [[ ! -f "$VG_PREFIX/libhandlegraph.commit" ]] ||
           [[ "$(cat "$VG_PREFIX/libhandlegraph.commit")" != ae42926da7743a7108db0474bfcf1a1cdac34abb ]]; then
            printf 'Freeze the original shared library with freeze_control.sh first\n' >&2; exit 2
        fi
    fi
esac
env | LC_ALL=C sort | grep -E '^(VG_BENCH_|OMP_NUM_THREADS=|LD_LIBRARY_PATH=)' > "$OUT/environment.log"
printf '%q ' "${COMMAND[@]}" > "$OUT/command.txt"
printf '\n' >> "$OUT/command.txt"
python3 "$REPO/benchmarks/cactus_unchop/monitor.py" "$OUT" --output-name "$OUTPUT" \
    /usr/bin/time -v -o "$OUT/time.log" "${COMMAND[@]}"
