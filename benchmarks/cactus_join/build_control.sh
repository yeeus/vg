#!/usr/bin/env bash
# Build the original vg with only the VCF header fix.
set -euo pipefail
SOURCE="$(realpath "${1:?Usage: build_control.sh original_vg_source new_output [build_jobs]}")"
OUT="${2:?new output directory}"
JOBS="${3:-8}"
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PIN=f2ed0bbd4f7d1e7f8c8f4df4a84018f388194d51
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]]
[[ "$(git -C "$SOURCE" rev-parse HEAD)" == "$PIN" ]]
git -C "$SOURCE" diff --exit-code HEAD -- .
submodules="$(git -C "$SOURCE" submodule status --recursive)"
if grep '^[+U-]' <<< "$submodules"; then
    printf 'Check out all pinned control submodules before building.\n' >&2
    exit 1
fi
git -C "$SOURCE" apply --check "$HERE/patches/deconstruct-header.patch"
mkdir "$OUT"
OUT="$(realpath "$OUT")"
mkdir "$OUT/bin" "$OUT/lib"
git -C "$SOURCE" apply "$HERE/patches/deconstruct-header.patch"
make -C "$SOURCE" -j "$JOBS" bin/vg > "$OUT/build.log" 2>&1
cp -L "$SOURCE/bin/vg" "$OUT/bin/vg"
for library in "$SOURCE"/lib/*.so*; do
    [[ -e "$library" ]] && cp -a "$library" "$OUT/lib/"
done
python3 "$HERE/test_deconstruct.py" "$OUT/bin/vg" "$OUT/bin/vg" | tee "$OUT/test.log"
printf '%s + deconstruct-header.patch\n' "$PIN" > "$OUT/source.commit"
printf 'PASS fixed control: %s\n' "$OUT"
