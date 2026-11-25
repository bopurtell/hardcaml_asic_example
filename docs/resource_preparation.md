# Project-owned resource preparation

Resource preparation is distinct from source-build and bundle generation.

Both CLIs link `hardcaml_asic.execution`. They select and construct ordinary OCaml
projects inside `Preparation_service.run_cli`'s closure, after durable allocation,
then call `Project.prepare_resources ~on_phase`. The provider owns schema,
identities, storage and inspection; the example adds no serializer or store.

## Build with the installed provider (PDK-free)

Follow the [README](../README.md) to install the provider in opam. From the
example checkout, in that activated compiler environment:

```sh
dune build -j6 asics/fifo_demo/cli/chip.exe asics/program_memory/cli/chip.exe
MEMORY="$PWD/_build/default/asics/program_memory/cli/chip.exe"
FIFO="$PWD/_build/default/asics/fifo_demo/cli/chip.exe"
PROVIDER=$(command -v hardcaml-asic-flow)
```

The provider's `--version --json` must advertise `preparation1: true`.
Resource preparation is independent of the physical toolchain and Silver.

## Durable and live commands

```sh
"$MEMORY" prepare --selection exact --operation synthesis \
  --source-root "$PWD" --results-root "$PWD/_flow_results/preparation" --json
"$FIFO" prepare --source-root "$PWD" \
  --results-root "$PWD/_flow_results/preparation" --json

# ATTEMPT comes from the first JSONL event, not from a guessed directory name.
"$PROVIDER" preparation-inspect "$ATTEMPT" --json
"$PROVIDER" preparation-inspect "$ATTEMPT" --current-identity "$CURRENT_ID" --json

# Complete current implementation preparation, no publication:
"$MEMORY" preview --selection exact --operation synthesis --source-root "$PWD" --json
"$FIFO" preview --source-root "$PWD" --json

# Pure inventory, no source observation or persistence:
"$MEMORY" resources --selection exact --operation synthesis --json
"$MEMORY" resources --selection exact --operation synthesis --simulation --json
"$FIFO" resources --json
```

`prepare --json` emits flushed allocation then terminal JSONL. Preserve the
nonzero exit and inspect the allocated attempt even after failure. Retries always
allocate fresh attempts. Generic inspection loads retained evidence without
project code, current sources, PDK or EDA. Failed attempts have `preparation: null`,
whereas successful FIFO preparation has an explicit empty resource list. Reader
exit 0 means a valid inspection, not necessarily a successful preparation; corrupt
evidence/query exits 2. No project inspection wrapper is needed.

Memory commands require explicit selection (`flops`, `exact`, `fallback`) and
operation (`synthesis`, `hardening`). `--depth 128` is a real 128×16 constructor:
Exact rejects it, while fallback selects flops with `flop_fallback` reason.
The default remains 256×16. Both operations are preparation-only here.

`resources` defaults to resolved Implementation. `--simulation` deliberately uses
ordinary Simulation elaboration; an Exact selection still builds a behavioral
model, not the selected macro. It has no preparation/source identity. `preview`
has full preparation/source/configuration/circuit identities, is always
Implementation, and writes nothing. A preview identity can be supplied explicitly
to historical inspection; the inspector never calculates current state itself.

## Identity and source coverage

Preparation observes declared source inputs before/after elaboration and retains
hashes, Git status and revision. Configuration and actual deterministic circuit
RTL have separate identities. Attempt IDs and paths are lifecycle references,
not content identities. Preparation has no bundle identity. These observations
**do not prove that the compiled constructor was built from those source bytes**;
`compiled_source_proven`, `p6_source_stamp`, collateral-file verification and
measured-evidence coverage are explicitly false. Collateral references and RTL
instance linkage are not PDK presence or synthesis-retention evidence.

When adding project implementation dependencies, extend `source_inputs` in
`asics/program_memory/project/program_memory.ml` or `asics/fifo_demo/project/fifo_chip.ml`. The focused checker gates the
current constructor/CLI dependencies; new shared production helpers must be added
to both inventories and that gate. Test scripts and retained acceptance files are
not constructor dependencies.

## Focused verification

```sh
python3 -B scripts/check_prepare.py --memory "$MEMORY" --fifo "$FIFO" \
  --provider "$PROVIDER" --source-root "$PWD"
```

The checker never builds or launches EDA. It uses a disposable source fixture
inside `.dev` and covers source/config/circuit identity changes, historical
source removal, corruption, retries, Simulation roles and the empty FIFO
resource list. The historical capture records are archived separately.
