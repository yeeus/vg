#!/usr/bin/env bash
set -euo pipefail
PREFIX="${1:?Usage: build.sh new_prefix original_vg [build_jobs]}"
ORIGINAL="$(realpath "${2:?original vg f2ed0bbd4 binary}")"
JOBS="${3:-16}"
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]]
mkdir -p "$(dirname "$PREFIX")"
mkdir "$PREFIX"
PREFIX="$(realpath "$PREFIX")"
mkdir "$PREFIX/source" "$PREFIX/candidate" "$PREFIX/candidate/bin" "$PREFIX/candidate/lib"
git -C "$REPO" rev-parse HEAD > "$PREFIX/source.commit"
python3 -c 'import psutil'

# The only shared vg dependency reported by the original installation was
# libhandlegraph. Rebuild its ORIGINAL pin into a completely separate prefix.
bash "$REPO/benchmarks/cactus_unchop/freeze_control.sh" "$ORIGINAL" "$PREFIX/control" "$JOBS"
ln -s vg.control "$PREFIX/control/bin/vg"

# Keep the original dependency pins. Patch content is versioned in this repo.
# These two upstream URLs use the obsolete git:// transport in the old tree.
git -C "$REPO" config submodule.deps/cairo.url https://gitlab.freedesktop.org/cairo/cairo.git
git -C "$REPO" config submodule.deps/pixman.url https://gitlab.freedesktop.org/pixman/pixman.git
git -C "$REPO" submodule update --init --recursive
git -C "$REPO/deps/libbdsg" apply --check "$HERE/patches/membership.patch"
git -C "$REPO/deps/libbdsg" apply "$HERE/patches/membership.patch"
make -C "$REPO" -j "$JOBS" > "$PREFIX/build.vg.log" 2>&1
cp "$REPO/bin/vg" "$PREFIX/candidate/bin/vg"
for library in "$REPO"/lib/*.so*; do
    [[ -e "$library" ]] && cp -a "$library" "$PREFIX/candidate/lib/"
done

# GFAffix: same compiler, dependency lock and original 0.2.2 source for both.
git clone --no-checkout https://github.com/codialab/GFAffix.git "$PREFIX/source/gfaffix"
git -C "$PREFIX/source/gfaffix" checkout --detach c15a8ca0058652e799f10e39f5bbc6f20a115292
cp "$HERE/patches/gfaffix.Cargo.lock" "$PREFIX/source/gfaffix/Cargo.lock"
(cd "$PREFIX/source/gfaffix" && cargo build --release --locked -j "$JOBS") > "$PREFIX/build.gfaffix.control.log" 2>&1
cp "$PREFIX/source/gfaffix/target/release/gfaffix" "$PREFIX/control/bin/"
git -C "$PREFIX/source/gfaffix" apply --check "$HERE/patches/gfaffix.patch"
git -C "$PREFIX/source/gfaffix" apply "$HERE/patches/gfaffix.patch"
(cd "$PREFIX/source/gfaffix" && cargo build --release --locked -j "$JOBS") > "$PREFIX/build.gfaffix.candidate.log" 2>&1
cp "$PREFIX/source/gfaffix/target/release/gfaffix" "$PREFIX/candidate/bin/"

# clip-vg.cpp depends only on these graph libraries, not on HAL conversion.
# Build the pinned Cactus clip-vg source directly, with its OWN pinned backend.
git clone --no-checkout https://github.com/ComparativeGenomicsToolkit/hal2vg.git "$PREFIX/source/hal2vg"
git -C "$PREFIX/source/hal2vg" checkout --detach 80112aa3de68be015093bb88c784f7911a74b09d
git -C "$PREFIX/source/hal2vg" submodule update --init deps/jemalloc
JEM="$PREFIX/source/hal2vg/deps/jemalloc"
(
    cd "$JEM"
    export CFLAGS='-O3 -g' CXXFLAGS='-O3 -g' LDFLAGS='' LIBS=''
    ./autogen.sh
    ./configure --disable-libdl
    make -j "$JOBS" build_lib_static
) > "$PREFIX/build.jemalloc.log" 2>&1
git -C "$PREFIX/source/hal2vg" submodule update --init --recursive deps/libbdsg-easy
EASY="$PREFIX/source/hal2vg/deps/libbdsg-easy"
[[ "$(git -C "$EASY/deps/libbdsg" rev-parse HEAD)" == a2e873b80b10b38b90f1f82bee3044116b6276fc ]]
make -C "$EASY" -j "$JOBS" > "$PREFIX/build.clip.control.log" 2>&1
compile_clip() {
    "${CXX:-g++}" -O3 -g -UNDEBUG -std=c++20 -DHAVE_JEMALLOC -fopenmp -pthread \
        -I "$EASY/include" "$PREFIX/source/hal2vg/clip-vg.cpp" \
        "$EASY/lib/libbdsg.a" "$EASY/lib/libhandlegraph.a" "$EASY/lib/libsdsl.a" \
        "$EASY/lib/libdivsufsort.a" "$EASY/lib/libdivsufsort64.a" \
        "$JEM/lib/libjemalloc.a" -ljansson -ldl -o "$1"
}
compile_clip "$PREFIX/control/bin/clip-vg" >> "$PREFIX/build.clip.control.log" 2>&1
git -C "$EASY/deps/libbdsg" apply --check "$HERE/patches/membership.clip.patch"
git -C "$EASY/deps/libbdsg" apply "$HERE/patches/membership.clip.patch"
# The upstream wrapper does not track headers in the installed archive.
make -C "$EASY/deps/libbdsg" clean > "$PREFIX/build.clip.candidate.log" 2>&1
make -C "$EASY/deps/libbdsg" -j "$JOBS" \
    CPLUS_INCLUDE_PATH="$EASY/include${CPLUS_INCLUDE_PATH:+:$CPLUS_INCLUDE_PATH}" \
    LIBRARY_PATH="$EASY/lib${LIBRARY_PATH:+:$LIBRARY_PATH}" >> "$PREFIX/build.clip.candidate.log" 2>&1
cp "$EASY/deps/libbdsg/lib/libbdsg.a" "$EASY/lib/libbdsg.a"
cp -a "$EASY/deps/libbdsg/bdsg/include/." "$EASY/include/"
compile_clip "$PREFIX/candidate/bin/clip-vg" >> "$PREFIX/build.clip.candidate.log" 2>&1

python3 "$HERE/prepare.py" "$PREFIX/control/override" --mode control
python3 "$HERE/prepare.py" "$PREFIX/candidate/override" --mode candidate
git -C "$REPO" submodule status --recursive > "$PREFIX/dependencies.log"
git -C "$PREFIX/source/hal2vg" submodule status --recursive >> "$PREFIX/dependencies.log"
python3 "$REPO/benchmarks/cactus_unchop/test_gfaffix.py" \
    "$PREFIX/control/bin/gfaffix" "$PREFIX/candidate/bin/gfaffix" "$PREFIX/source/gfaffix/examples"
python3 "$HERE/test_checkpoint.py"
python3 "$HERE/test_join.py" "$PREFIX" --sequential
printf 'Build and small differential checks passed: %s\n' "$PREFIX"
