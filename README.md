# Hardcaml ASIC example: controlled FIFO

A standalone Hardcaml hardware design with a Tiny Tapeout CMOS5L wrapper,
independent FIFO verification, immutable implementation bundles and named ASIC
flows. The default target is a 16×8 register-backed FIFO with synchronous
active-high clear and registered pop response. Silver is optional; neither its
application nor its OCaml provider SDK is needed for the standalone steps.

The example code is [MIT-licensed](LICENSE). It is an independent project built
on Hardcaml, not a Jane Street project.

## 1. Clone the example and install a compatible provider

Use Linux with Git, opam, Bash, Python 3.9+ and standard Unix utilities. The
example uses OxCaml; install its system build prerequisites via your distribution.
Use a separate opam switch if you do not want to change an existing environment.

On Ubuntu, install the host tools:

```sh
sudo apt update
sudo apt install -y autoconf bubblewrap build-essential bzip2 ca-certificates curl git \
  libgmp-dev opam pkg-config python3 rsync unzip xz-utils zlib1g-dev
```

Clone the example:

```sh
git clone --branch oxcaml https://github.com/bopurtell/hardcaml_asic_example.git
cd hardcaml_asic_example
```

For a fresh opam installation and switch, run:

```sh
opam init --bare --no-setup
if ! opam switch list --short | grep -Fxq '5.2.0+ox'; then
  opam switch create 5.2.0+ox ocaml-variants.5.2.0+ox \
    --repos ox=git+https://github.com/oxcaml/opam-repository.git,default
fi
eval "$(opam env --switch=5.2.0+ox --set-switch)"
```

The switch is reused if already present. In the activated switch, install the
provider directly from the repository and exact committed revision recorded in
[`asic-dependency.json`](asic-dependency.json). No provider checkout is needed:

```sh
ASIC_SOURCE=$(python3 -c 'import json; r=json.load(open("asic-dependency.json")); print("git+" + r["repository"] + "#" + r["revision"])')
opam pin add --no-action hardcaml_asic "$ASIC_SOURCE"
opam install hardcaml_asic expect_test_helpers_core
hardcaml-asic-flow --version --json
```

The installed CLI should advertise contract 4 and `namedflow1: true`. Keep the
provider's executable and libraries in the same switch. The package version alone
is not a source-revision stamp. Bootstrap does not reinstall or upgrade the
selected provider.

## 2. Build and verify the example (no PDK or physical EDA)

Run from the example root, in the activated switch:

```sh
dune build -j6 @standalone
```

This builds both chip CLIs and runs the FIFO Cyclesim/model comparison, ASIC
wrapper, resolution and catalog checks, bundle verification, program-memory
behavioral tests, and SRAM budget/resource checks. Generated-Verilog replay is
included when Icarus Verilog (`iverilog` and `vvp`) is available; otherwise
the replay is explicitly skipped. To require FIFO Verilog replay, install
Icarus Verilog and run:

```sh
dune build -j6 @asics/fifo_demo/verif/bundle/acceptance-strict
```

The `@standalone` alias excludes the optional Silver simulation adapter and
requires no SDK, PDK, Docker or physical EDA. It does not change the default
whole-tree build.

## 3. Inspect, plan and emit (still PDK-free)

```sh
CHIP="$PWD/_build/default/asics/fifo_demo/cli/chip.exe"
"$CHIP" describe --json
"$CHIP" flow list --json
mkdir -p _flow_results
OUTPUT=$(mktemp -d "$PWD/_flow_results/preview.XXXXXX")
"$CHIP" flow plan --flow standard --profile balanced --endpoint synthesis --json > "$OUTPUT/plan.json"
IDENTITY=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["plan_identity"])' "$OUTPUT/plan.json")
"$CHIP" flow emit --flow standard --profile balanced --endpoint synthesis \
  --expected-plan-identity "$IDENTITY" --results-root "$OUTPUT" --json
```

The plan identifies the exact source/flow selection; emission publishes an
immutable bundle containing RTL, resolved target configuration and manifest.
Neither step runs synthesis. Replan after changing source or selected options.
The FIFO catalog contains `standard/balanced` and `standard/synth_delay`.

## 4. Optional: provision physical tools, run synthesis and read results

Physical execution requires Docker and the provider's pinned LibreLane, TT and
IHP PDK collateral (allow several GB). Full acceptance also requires Nix/precheck.
Bootstrap provisions tools only; it does not install OCaml packages, build the
project or configure Silver by default.

```sh
TOOLS="$PWD/_flow_tools"
./bootstrap.sh --toolchain "$TOOLS"
./bootstrap.sh --toolchain "$TOOLS" --check
```

Tool selection is `--toolchain PATH`, then `TOOLCHAIN`, then this checkout's
`_flow_tools/`. The check is read-only. `--offline` and `--no-container` are
provider options; skipping container checks does not certify physical readiness.
Run the actual FIFO synthesis through the installed provider:

```sh
mkdir -p _flow_results
SESSION=$(mktemp -d "$PWD/_flow_results/headless.XXXXXX")
python3 -B scripts/headless_flow.py \
  --project "$CHIP" --provider "$(command -v hardcaml-asic-flow)" \
  --source-root "$PWD" --results-root "$SESSION/results" --toolchain "$TOOLS" \
  --flow standard --profile balanced --endpoint synthesis \
  --stage-timeout 3600 --timeout 7200 --receipt "$SESSION/synthesis.json"
```

See the [headless flow guide](docs/headless_flow.md) for preview, report and
reconnect commands, direct CLI execution, and extending to signoff. A successful
execution is not physical acceptance.

## 5. Optional: Silver integration

Silver is a separate workbench. For synthesis/preparation alone, install Silver
and run the synthesis configuration; for simulation also install the Silver
OCaml provider SDK. See [Silver setup and compatibility](docs/silver.md). Existing
configuration and saved runs are retained. `./bootstrap.sh --with-silver` explicitly
requests the former combined provision-and-configure behavior; it requires the
SDK and is not part of standalone setup.

<a id="chip-target-cli"></a>

## Other targets and source layout

| Location | Purpose |
| --- | --- |
| [`ip/controlled_fifo/`](ip/controlled_fifo/) | RTL, independent model, stimulus, Cyclesim tests and optional simulation adapter |
| [`asics/fifo_demo/`](asics/fifo_demo/) | TT top, chip declaration, named flows, CLI and wrapper/bundle replay |
| [`asics/program_memory/`](asics/program_memory/README.md) | SRAM example with its own target and qualification |
| [`asics/sram_budget/`](asics/sram_budget/README.md) | Competing requests for a chip-level SRAM budget |
| [`tooling_acceptance/`](tooling_acceptance/) | Timing, variants and workload fixtures |
| [`integration/workbench/`](integration/workbench/) | Optional Silver provider integration |

IP owns RTL and component verification; ASICs own their tops and system
verification. See [repository layout](docs/repository_layout.md) and the
[documentation index](docs/README.md). The installed `hardcaml-asic-targets list`
command discovers registered targets from `hardcaml-asic-targets.json`; build the
selected target's executable before invoking it. For example:

```sh
hardcaml-asic-targets list
dune build -j6 asics/program_memory/cli/chip.exe
hardcaml-asic-targets exec --target program_memory -- flow list --json
```

Generated builds, tools, results and local Silver configuration are separate
from source. Keep the total concurrent build job allocation at or below 20.
