#!/usr/bin/env bash
# Reuse the r2 runtime and rebuild only the candidate clip-vg.
set -euo pipefail
OLD="$(realpath "${1:?Usage: upgrade_r3.sh r2_prefix fixed_control new_r3_prefix [build_jobs]}")"
FIXED="$(realpath "${2:?build_control.sh output directory}")"
NEW="${3:?new r3 prefix}"
JOBS="${4:-8}"
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]]
grep -Fxq 'f2ed0bbd4f7d1e7f8c8f4df4a84018f388194d51 + deconstruct-header.patch' "$FIXED/source.commit"
HAL="$OLD/source/hal2vg"
JEM="$HAL/deps/jemalloc"
R1="$(cat "$OLD/reused_r1.prefix")"
EASY="$R1/source/hal2vg/deps/libbdsg-easy"
PIN=a2e873b80b10b38b90f1f82bee3044116b6276fc
[[ "$(git -C "$HAL" rev-parse HEAD)" == 80112aa3de68be015093bb88c784f7911a74b09d ]]
[[ "$(git -C "$OLD/source/libbdsg-candidate" rev-parse HEAD)" == "$PIN" ]]
test -f "$JEM/lib/libjemalloc.a"
test -f "$EASY/lib/libhandlegraph.a"
python3 -c 'import psutil; import cactus'
mkdir "$NEW"
NEW="$(realpath "$NEW")"
git -C "$REPO" rev-parse HEAD > "$NEW/source.commit"
for mode in control candidate; do
    mkdir -p "$NEW/$mode/bin" "$NEW/$mode/lib"
    cp -L "$OLD/$mode/bin/gfaffix" "$NEW/$mode/bin/"
done
cp -L "$FIXED/bin/vg" "$NEW/control/bin/vg"
cp -a "$FIXED/lib/." "$NEW/control/lib/"
cp -L "$OLD/control/bin/clip-vg" "$NEW/control/bin/"
cp -L "$OLD/candidate/bin/vg" "$NEW/candidate/bin/vg"
cp -a "$OLD/candidate/lib/." "$NEW/candidate/lib/"
mkdir "$NEW/source"
BDSG="$NEW/source/libbdsg-candidate"
git clone --no-checkout "$OLD/source/libbdsg-candidate" "$BDSG"
git -C "$BDSG" checkout --detach "$PIN"
git -C "$BDSG" apply "$HERE/patches/membership.clip.patch" "$HERE/patches/clip-step-transfer.patch"
git -C "$HAL" show HEAD:clip-vg.cpp > "$NEW/source/clip-vg.cpp"
(cd "$NEW/source"; git apply --no-index "$HERE/patches/clip-memory.patch")
(
    export CPLUS_INCLUDE_PATH="$EASY/include${CPLUS_INCLUDE_PATH:+:$CPLUS_INCLUDE_PATH}"
    export LIBRARY_PATH="$EASY/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
    make -C "$BDSG" -j "$JOBS"
    "${CXX:-g++}" -O3 -g -UNDEBUG -std=c++20 -DHAVE_JEMALLOC -fopenmp -pthread \
        -I "$BDSG/bdsg/include" -I "$EASY/include" "$NEW/source/clip-vg.cpp" \
        "$BDSG/lib/libbdsg.a" "$EASY/lib/libhandlegraph.a" "$EASY/lib/libsdsl.a" \
        "$EASY/lib/libdivsufsort.a" "$EASY/lib/libdivsufsort64.a" \
        "$JEM/lib/libjemalloc.a" -ljansson -ldl -o "$NEW/candidate/bin/clip-vg"
) > "$NEW/build.clip.candidate.log" 2>&1
nm "$NEW/candidate/bin/clip-vg" | awk '$3 == "malloc_conf" {found=1} END {exit !found}'
for mode in control candidate; do
    python3 "$HERE/prepare.py" "$NEW/$mode/override" --mode "$mode"
done
python3 "$HERE/test_deconstruct.py" "$NEW/control/bin/vg" "$NEW/candidate/bin/vg"
python3 "$HERE/test_join.py" "$NEW" --sequential
printf 'PASS r3 control and candidate: %s\n' "$NEW"
