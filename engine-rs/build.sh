#!/usr/bin/env bash
# Build l4m-engine.
#
# Bindgen needs libclang, which a slim box often lacks. whisper-rs-sys ships
# pre-generated bindings, so skip bindgen entirely; cmake is still needed to
# compile whisper.cpp.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# rustup installs into ~/.cargo/bin; non-login shells often miss it.
if [ -d "$HOME/.cargo/bin" ]; then
    PATH="$HOME/.cargo/bin:$PATH"
fi

if ! command -v cargo >/dev/null 2>&1; then
    echo "cargo not found: install rustup (https://rustup.rs)" >&2
    exit 1
fi

if ! command -v cmake >/dev/null 2>&1; then
    if [ -x ../.venv/bin/cmake ]; then
        PATH="$(cd ../.venv/bin && pwd):$PATH"
    else
        echo "cmake not found: apt-get install cmake, or pip install cmake" >&2
        exit 1
    fi
fi

export WHISPER_DONT_GENERATE_BINDINGS=1
exec cargo build --release "$@"
