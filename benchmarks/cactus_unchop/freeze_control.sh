#!/usr/bin/env bash
set -euo pipefail
ORIGINAL="$(realpath "${1:?Usage: freeze_control.sh original_vg.control new_prefix [build_threads]}")"
PREFIX="$2"
THREADS="${3:-4}"
VERSION="$("$ORIGINAL" version 2>&1)"
if [[ "$VERSION" != *f2ed0bbd4* ]]; then
    printf 'Expected original vg f2ed0bbd4, got: %s\n' "$VERSION" >&2
    exit 2
fi
mkdir -p "$(dirname "$PREFIX")"
mkdir "$PREFIX"
PREFIX="$(realpath "$PREFIX")"
git clone --filter=blob:none --no-checkout https://github.com/yeeus/libhandlegraph.git "$PREFIX/source"
git -C "$PREFIX/source" checkout --detach ae42926da7743a7108db0474bfcf1a1cdac34abb
cmake -S "$PREFIX/source" -B "$PREFIX/build" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PREFIX" -DCMAKE_INSTALL_LIBDIR=lib
cmake --build "$PREFIX/build" --parallel "$THREADS"
cmake --install "$PREFIX/build"
mkdir "$PREFIX/bin"
cp "$ORIGINAL" "$PREFIX/bin/vg.control"
export LD_LIBRARY_PATH="$PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
"$PREFIX/bin/vg.control" version > "$PREFIX/version.log" 2>&1
ldd "$PREFIX/bin/vg.control" > "$PREFIX/libraries.log" 2>&1 || true
if grep -q 'libhandlegraph.so' "$PREFIX/libraries.log"; then
    grep 'libhandlegraph.so' "$PREFIX/libraries.log" | grep -F "$PREFIX/lib/"
fi
printf '%s\n' ae42926da7743a7108db0474bfcf1a1cdac34abb > "$PREFIX/libhandlegraph.commit"
printf 'Frozen control: %s/bin/vg.control\n' "$PREFIX"
