#!/bin/bash
set -eu

if ! command -v hardcaml-asic-flow >/dev/null 2>&1; then
    printf '%s\n' 'bootstrap: hardcaml-asic-flow is required on PATH.' \
        'Install a compatible hardcaml_asic provider via opam and activate its environment,' \
        'or explicitly refresh the development provider and source .dev/asic/current/activate.sh (see README.md).' >&2
    exit 127
fi

script_dir=${BASH_SOURCE[0]%/*}
if [[ $script_dir == "${BASH_SOURCE[0]}" ]]; then
    script_dir=.
fi
project_root=$(CDPATH= cd -- "$script_dir" && pwd -P)
default_tools=${TOOLCHAIN:-$project_root/_flow_tools}
provision=(hardcaml-asic-flow provision --toolchain "$default_tools" "$@")
tools=$default_tools
# Only configure after a provisioning run. Delegate informational modes and
# unknown arguments directly, retaining the installed CLI's diagnostics/status.
while (($#)); do
    case $1 in
        --toolchain) (($# >= 2)) || exec "${provision[@]}"; tools=$2; shift ;;
        --toolchain=*) tools=${1#*=} ;;
        --python) (($# >= 2)) || exec "${provision[@]}"; shift ;;
        --python=*|--offline|--no-container) ;;
        *) exec "${provision[@]}" ;;
    esac
    shift
done
"${provision[@]}"
python3 -B "$project_root/scripts/configure-synthesis.py" --toolchain="$tools"
exec python3 -B "$project_root/scripts/configure-simulation.py" --toolchain="$tools"
