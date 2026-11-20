#!/usr/bin/env bash
# Usage: scripts/build_with_asic_checkout.sh [DUNE_TARGET ...]
# Overrides: HARDCAML_ASIC_CHECKOUT, ASIC_EXAMPLE_BUILD_DIR, WORKBENCH_SDK_PREFIX,
# OPAMSWITCH (defaults to 5.2.0+ox). Relative overrides resolve from the caller.
set -euo pipefail
example=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
export HARDCAML_ASIC_CHECKOUT
HARDCAML_ASIC_CHECKOUT=$(cd -- "${HARDCAML_ASIC_CHECKOUT:-$example/../hardcaml_asic}" && pwd -P)
build=$(realpath -m -- "${ASIC_EXAMPLE_BUILD_DIR:-$example/_build_asic_dev}")
sdk=$(realpath -m -- "${WORKBENCH_SDK_PREFIX:-$example/.dev/workbench-provider-sdk}")
if [[ $build == "$(realpath -m -- "$example/_build")" ]]; then
    echo "Choose a private ASIC_EXAMPLE_BUILD_DIR; _build belongs to the prepared example." >&2
    exit 2
fi

switch_env=$(opam env --switch="${OPAMSWITCH:-5.2.0+ox}" --set-switch --shell=sh)
eval "$switch_env"
(cd "$HARDCAML_ASIC_CHECKOUT" && dune build --root . --build-dir _build -j4 @install)

prefix=$HARDCAML_ASIC_CHECKOUT/_build/install/default
export OCAMLPATH="$prefix/lib:$sdk/lib${OCAMLPATH:+:$OCAMLPATH}"
export PATH="$prefix/bin:$PATH"
unset HARDCAML_ASIC_GENERATION
cd "$example"
if (( $# == 0 )); then set -- asics/fifo_demo/cli/project.exe; fi
exec dune build --root . --build-dir "$build" -j4 "$@"
