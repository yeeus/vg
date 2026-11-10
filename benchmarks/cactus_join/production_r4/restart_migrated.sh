#!/usr/bin/env bash
# Resume a relocated, original Cactus join jobStore with the frozen r4 runtime.
set -eo pipefail
source ./cactus.config.sh
set -u

SOFT="${R4_SOFT:-/public/home/u12518101/softwares}"
TOOLS="$SOFT/cactus-r4-run"
exec 9> "$PWD/.join_r4.lock"
flock -n 9 || { echo 'Another r4 run/restart holds this chromosome lock' >&2; exit 1; }

exec python3 "$TOOLS/migrate_join.py" \
    --src "$SOFT/vg-join-candidate-r4" --prefix "$SOFT/cactus-join-candidate-r4" \
    --chrom "${CHROM:?}" --sv-gfa "${GFA:?}" --reference "${REFERENCES[@]}" "$@"
