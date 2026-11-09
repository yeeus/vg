#!/usr/bin/env bash
# r3 plus one clip-vg backend change; preserve both previous installations.
set -euo pipefail
OLD="$(realpath "${1:?Usage: upgrade_r4.sh r3_prefix r2_build_prefix new_r4_prefix [build_jobs]}")"
R2="$(realpath "${2:?r2 build prefix on cluster A}")"
NEW="${3:?new r4 prefix}"
JOBS="${4:-8}"
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]]
PIN=a2e873b80b10b38b90f1f82bee3044116b6276fc
HAL="$R2/source/hal2vg"
JEM="$HAL/deps/jemalloc"
R1="$(cat "$R2/reused_r1.prefix")"
EASY="$R1/source/hal2vg/deps/libbdsg-easy"
[[ "$(git -C "$HAL" rev-parse HEAD)" == 80112aa3de68be015093bb88c784f7911a74b09d ]]
[[ "$(git -C "$OLD/source/libbdsg-candidate" rev-parse HEAD)" == "$PIN" ]]
test -f "$JEM/lib/libjemalloc.a"
test -f "$EASY/lib/libhandlegraph.a"
test -f "$OLD/candidate/override/cactus/refmap/cactus_graphmap_join.py"
mkdir "$NEW"
NEW="$(realpath "$NEW")"
git -C "$REPO" rev-parse HEAD > "$NEW/source.commit"
printf '%s\n' "$OLD" > "$NEW/reused_r3.prefix"
cp -a "$OLD/candidate" "$NEW/candidate"
mkdir "$NEW/source"
BDSG="$NEW/source/libbdsg-candidate"
git clone --no-checkout "$OLD/source/libbdsg-candidate" "$BDSG"
git -C "$BDSG" checkout --detach "$PIN"
git -C "$BDSG" apply "$HERE/patches/membership.clip.patch" \
    "$HERE/patches/clip-step-transfer.patch"
git -C "$BDSG" apply --check "$HERE/patches/clip-path-growth.patch"
git -C "$BDSG" apply "$HERE/patches/clip-path-growth.patch"
git -C "$HAL" show HEAD:clip-vg.cpp > "$NEW/source/clip-vg.cpp"
(cd "$NEW/source"; git apply --no-index "$HERE/patches/clip-memory.patch")
(
    export CPLUS_INCLUDE_PATH="$EASY/include${CPLUS_INCLUDE_PATH:+:$CPLUS_INCLUDE_PATH}"
    export LIBRARY_PATH="$EASY/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
    make -C "$BDSG" -j "$JOBS"
    common=("$BDSG/lib/libbdsg.a" "$EASY/lib/libhandlegraph.a" "$EASY/lib/libsdsl.a"
            "$EASY/lib/libdivsufsort.a" "$EASY/lib/libdivsufsort64.a"
            "$JEM/lib/libjemalloc.a" -ljansson -ldl)
    "${CXX:-g++}" -O3 -g -UNDEBUG -std=c++20 -DHAVE_JEMALLOC -fopenmp -pthread \
        -I "$BDSG/bdsg/include" -I "$EASY/include" "$NEW/source/clip-vg.cpp" \
        "${common[@]}" -o "$NEW/candidate/bin/clip-vg"
    "${CXX:-g++}" -O2 -UNDEBUG -std=c++20 -fopenmp -pthread \
        -I "$BDSG/bdsg/include" -I "$EASY/include" "$HERE/test_clip_growth.cpp" \
        "${common[@]}" -o "$NEW/source/test_clip_growth"
) > "$NEW/build.clip.candidate.log" 2>&1
nm "$NEW/candidate/bin/clip-vg" | awk '$3 == "malloc_conf" {found=1} END {exit !found}'
python3 "$HERE/test_clip_growth.py" "$OLD" "$NEW"
printf 'PASS r4 clip-vg build and exact graph checks: %s\n' "$NEW"
