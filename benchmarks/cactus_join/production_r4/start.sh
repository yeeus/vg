#!/usr/bin/env bash
# Run from the chromosome directory, with 56 CPUs and 500G allocated.
set -eo pipefail
source ./cactus.config.sh
set -u

SOFT=/public/home/u12518101/softwares
TOOLS="$SOFT/cactus-r4-run"
exec 9> "$PWD/.join_r4.lock"
flock -n 9 || { echo 'Another r4 run/restart holds this chromosome lock' >&2; exit 1; }

exec python3 "$TOOLS/launch.py" start \
    "$SOFT/vg-join-candidate-r4" "$SOFT/cactus-join-candidate-r4" \
    "$PWD/04.join.sh" "$PWD/join_r4" --memory 480Gi
