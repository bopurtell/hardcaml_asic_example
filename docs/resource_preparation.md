# Project-owned resource preparation

> **Source-layout note:** current CLIs are `asics/fifo_demo/cli/project.exe` and
> `asics/program_memory/project/memory_cli.exe`. Use the
> [layout map](repository_layout.md) for other source paths below. Resource
> preparation is distinct from Workbench source-build/bundle generation.

Both CLIs link `hardcaml_asic.execution`. They select and construct ordinary OCaml
projects inside `Preparation_service.run_cli`'s closure, after durable allocation,
then call `Project.prepare_resources ~on_phase`. The provider owns schema,
identities, storage and inspection; the example adds no serializer or store.

## Isolated installation and build

From the example checkout, after the provider APIs are ready:

```sh
opam exec --switch=5.2.0+ox -- python3 scripts/asic_dependency.py \
  --store "$PWD/.dev/asic-prepare" refresh \
  --source /home/wayne/devel/jane/hardcaml_asic --mode development --jobs 6
. "$PWD/.dev/asic-prepare/current/activate.sh"
opam exec --switch=5.2.0+ox -- dune build --build-dir _build_prepare -j6 \
  bin/project.exe memory/memory_cli.exe memory/test/memory_test.exe
MEMORY="$PWD/_build_prepare/default/memory/memory_cli.exe"
FIFO="$PWD/_build_prepare/default/bin/project.exe"
PROVIDER="$PWD/.dev/asic-prepare/current/bin/hardcaml-asic-flow"
```

Refresh builds captured provider bytes in a private directory and installs into
this store. It does not change the recorded dependency pin, SRAM/Workbench
selections or shared provider build. Keep consumer builds at `-j6` or lower.
`--version --json` must advertise `preparation1: true`.

The final review-corrected capture is generation
`a5de7cbfcc464e13ae1b5a5db6e39068`, provider snapshot SHA-256
`549cf74e17b4c8af34a7133ea3d983786adf5ce6c4d4e8914f62aff0a05e2f2a`.
Its receipt is retained in `acceptance/preparation/capture-final/report.json`.
New operations use workflow **descriptor v2**, with `circuit → snapshot →
source_after`; the outer operation/inspection schema remains 1. The installed
reader also accepts the exact original descriptor v1 without rewriting evidence.

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
`memory/program_memory.ml` or `asic/project.ml`. The focused checker gates the
current constructor/CLI dependencies; new shared production helpers must be added
to both inventories and that gate. Test scripts and retained acceptance files are
not constructor dependencies.

## Focused acceptance

```sh
python3 -B scripts/check_prepare.py --memory "$MEMORY" --fifo "$FIFO" \
  --provider "$PROVIDER" --source-root "$PWD" \
  --historical-dir "$PWD/acceptance/preparation/capture" \
  --output-dir "$PWD/acceptance/preparation/capture-final"

# Repeat without replacing retained acceptance (disposable fixtures only):
python3 -B scripts/check_prepare.py --memory "$MEMORY" --fifo "$FIFO" \
  --provider "$PROVIDER" --source-root "$PWD"
```

The output directory must be new. The compact archive retains the capture receipt,
CLI/executable metadata, check list, allocation/terminal delivery for all cases,
and portable exact/failed/FIFO attempt directories. The checker never builds or
launches EDA. It copies declared inputs into a disposable fixture inside `.dev`
so Git observation remains read-only. Source/config/circuit identity changes,
historical source removal, corruption, retry isolation, refused store destination,
Simulation roles, empty FIFO, and both operations are covered. Existing physical
replays are independent and need not be repeated.

The final checker also rejects named-pipe `operation.json` and `resources.json`
artifacts through the installed reader with a five-second timeout. It inspects
the original v1 exact/failure/FIFO attempts, explicitly compares matching and
different identities, and verifies the complete original archive's file hashes,
lengths, modification times and paths are unchanged. Results are retained in
`capture-final/historical-compatibility.json`. A matching supplied identity is
an equality comparison only; it does not establish compiled-source consistency.

An optional focused Dune alias is `@scripts/preparation-test`, with
`HARDCAML_ASIC_PREPARATION_PROVIDER` set to the absolute installed provider path
and `HARDCAML_ASIC_PREPARATION_SOURCE_ROOT` to the actual source checkout root.
It consumes Dune-built executables without a nested build. Direct invocation above
uses the actual source checkout and is the retained acceptance route.
