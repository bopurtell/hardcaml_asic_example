#!/bin/bash
# Run a command with the existing recorded/development provider activated.
# Installation/refresh is a separate explicit operation.
set -eu

if [[ $# == 0 ]]; then
    printf '%s\n' 'Usage: bash scripts/with_asic.sh COMMAND [ARG ...]' >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
activation="$script_dir/../.dev/asic/current/activate.sh"
if [[ ! -f $activation ]]; then
    printf '%s\n' 'No selected ASIC installation; see docs/dependency_commands.md for explicit refresh instructions.' >&2
    exit 1
fi
source "$activation"

# Check the execution sublibrary too: the old switch package is also version
# 0.1.0, but cannot compile the current project CLI.
ocamlfind query hardcaml_asic hardcaml_asic.execution >/dev/null
exec "$@"
