#!/usr/bin/env bash
# Reuse the r1 vg/GFAffix builds; rebuild only the pinned clip-vg toolchain.
set -euo pipefail
OLD="$(realpath "${1:?Usage: upgrade_r2.sh r1_prefix new_r2_prefix [build_jobs]}")"
NEW="${2:?new r2 prefix}"
JOBS="${3:-8}"
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]]
python3 -c 'import psutil; import cactus'
mkdir -p "$(dirname "$NEW")"
mkdir "$NEW"
NEW="$(realpath "$NEW")"
mkdir "$NEW/source"
git -C "$REPO" rev-parse HEAD > "$NEW/source.commit"
printf '%s\n' "$OLD" > "$NEW/reused_r1.prefix"
for mode in control candidate; do
    mkdir -p "$NEW/$mode/bin" "$NEW/$mode/lib"
    cp -L "$OLD/$mode/bin/vg" "$OLD/$mode/bin/gfaffix" "$NEW/$mode/bin/"
    cp -a "$OLD/$mode/lib/." "$NEW/$mode/lib/"
done

# Match the allocator and assertions selected by pinned hal2vg/include.mk.
# The previous manual r1 compile omitted jemalloc and used -DNDEBUG.
HAL="$NEW/source/hal2vg"
git clone --no-checkout "$OLD/source/hal2vg" "$HAL"
git -C "$HAL" checkout --detach 80112aa3de68be015093bb88c784f7911a74b09d
git -C "$HAL" submodule update --init deps/jemalloc
JEM="$HAL/deps/jemalloc"
(
    cd "$JEM"
    export CFLAGS='-O3 -g' CXXFLAGS='-O3 -g' LDFLAGS='' LIBS=''
    ./autogen.sh
    ./configure --disable-libdl
    make -j "$JOBS" build_lib_static
) > "$NEW/build.jemalloc.log" 2>&1
EASY="$OLD/source/hal2vg/deps/libbdsg-easy"
for mode in control candidate; do
    BDSG="$NEW/source/libbdsg-$mode"
    git clone --no-checkout "$EASY/deps/libbdsg" "$BDSG"
    git -C "$BDSG" checkout --detach a2e873b80b10b38b90f1f82bee3044116b6276fc
    if [[ "$mode" == candidate ]]; then
        git -C "$BDSG" apply --check "$HERE/patches/membership.clip.patch"
        git -C "$BDSG" apply "$HERE/patches/membership.clip.patch"
    fi
    (
        export CPLUS_INCLUDE_PATH="$EASY/include${CPLUS_INCLUDE_PATH:+:$CPLUS_INCLUDE_PATH}"
        export LIBRARY_PATH="$EASY/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
        make -C "$BDSG" -j "$JOBS"
        "${CXX:-g++}" -O3 -g -UNDEBUG -std=c++20 -DHAVE_JEMALLOC -fopenmp -pthread \
            -I "$BDSG/bdsg/include" -I "$EASY/include" "$HAL/clip-vg.cpp" \
            "$BDSG/lib/libbdsg.a" "$EASY/lib/libhandlegraph.a" "$EASY/lib/libsdsl.a" \
            "$EASY/lib/libdivsufsort.a" "$EASY/lib/libdivsufsort64.a" \
            "$JEM/lib/libjemalloc.a" -ljansson -ldl -o "$NEW/$mode/bin/clip-vg"
    ) > "$NEW/build.clip.$mode.log" 2>&1
    nm "$NEW/$mode/bin/clip-vg" | awk '$3 == "malloc_conf" {found=1} END {exit !found}'
    python3 "$HERE/prepare.py" "$NEW/$mode/override" --mode "$mode"
done
python3 "$HERE/test_checkpoint.py"
python3 "$HERE/test_join.py" "$NEW" --sequential
printf 'PASS r2 upgrade and small graph comparisons: %s\n' "$NEW"
