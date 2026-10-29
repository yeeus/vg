#!/usr/bin/env bash
set -euo pipefail
INPUT="$(realpath "${1:?Usage: prepare_input.sh align/chr21.vg outdir vg.control}")"
OUT="$2"
VG="$(realpath "$3")"
mkdir -p "$(dirname "$OUT")"
mkdir "$OUT"
OUT="$(realpath "$OUT")"
export OMP_NUM_THREADS=1 LC_ALL=C
"$VG" version > "$OUT/versions.log" 2>&1
gfaffix --version >> "$OUT/versions.log" 2>&1
"$VG" paths -x "$INPUT" -L > "$OUT/path_names.txt"
awk -F '#' '$1 == "GRCh38" { found=1 } END { exit !found }' "$OUT/path_names.txt"
# Exact full-phase preparation from Cactus 7f34bb7, defaultCores=1, reference[0]=GRCh38.
printf '%q ' "$VG" convert -f "$INPUT" > "$OUT/commands.txt"
printf '\n' >> "$OUT/commands.txt"
/usr/bin/time -v -o "$OUT/convert.time.log" \
    "$VG" convert -f "$INPUT" > "$OUT/chr21.vg.gfa" 2> "$OUT/convert.log"
printf '%q ' gfaffix "$OUT/chr21.vg.gfa" --output_refined "$OUT/chr21.vg.gfaffixed.gfa" \
    --check_transformation --threads 1 --dont_collapse 'GRCh38#[.]*' >> "$OUT/commands.txt"
printf '\n' >> "$OUT/commands.txt"
/usr/bin/time -v -o "$OUT/gfaffix.time.log" \
    gfaffix "$OUT/chr21.vg.gfa" --output_refined "$OUT/chr21.vg.gfaffixed.gfa" \
    --check_transformation --threads 1 --dont_collapse 'GRCh38#[.]*' \
    > "$OUT/gfaffix.stdout.log" 2> "$OUT/gfaffix.log"
printf 'Input ready: %s\n' "$OUT/chr21.vg.gfaffixed.gfa"
