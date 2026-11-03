#!/usr/bin/env bash
# Apply the header-only fix to an existing complete r1 vg build, then relink.
set -euo pipefail
BUILD="$(realpath "${1:?Usage: fix_deconstruct.sh vg_build new_output control_vg [jobs]}")"
OUT="${2:?new output directory}"
CONTROL="$(realpath "${3:?working control vg}")"
JOBS="${4:-8}"
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]]
test -f "$BUILD/obj/deconstructor.o"
test -f "$BUILD/lib/libvg.a"
git -C "$BUILD" apply --check "$HERE/patches/deconstruct-header.patch"
mkdir -p "$(dirname "$OUT")"
mkdir "$OUT"
OUT="$(realpath "$OUT")"
cp "$HERE/patches/deconstruct-header.patch" "$HERE/test_deconstruct.py" "$OUT/"
git -C "$BUILD" apply "$HERE/patches/deconstruct-header.patch"
# Do not clean: only the changed translation unit, archive and binary need work.
make -C "$BUILD" -j "$JOBS" bin/vg > "$OUT/build.log" 2>&1
python3 "$HERE/test_deconstruct.py" "$CONTROL" "$BUILD/bin/vg" > "$OUT/test.log" 2>&1
cat "$OUT/test.log"
cp -L "$BUILD/bin/vg" "$OUT/vg"
chmod 755 "$OUT/vg"
(cd "$OUT" && sha256sum vg > vg.sha256)
printf 'PASS incremental VCF header fix; transfer vg, vg.sha256 and test_deconstruct.py from %s\n' "$OUT"
