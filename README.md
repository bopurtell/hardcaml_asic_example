# Hardcaml ASIC development examples

Hardware projects and external-consumer qualification for `hardcaml_asic` and
Silver (formerly Hardcaml Workbench). The original design is a controlled FIFO ASIC; the repository
also includes a program-memory SRAM ASIC and small tool-qualification fixtures.

**First run on a fresh clone:** with `hardcaml_asic` and [Silver installed](../silver/README.md#install-and-open-silver),
run these from this example, in the switch where you installed the ASIC libraries:

```sh
./bootstrap.sh
silver
```

Bootstrap provisions the physical tools, builds the FIFO project CLI and
configures the checkout's Standard flow for Silver. After that, just run
`silver`. The provider on `PATH` supplies execution; the example's own CLI
supplies its flow catalog, including `standard / balanced / synthesis`.
For a checkout whose `_flow_tools` was provisioned before this setup step was
added, run `python3 -B scripts/configure-synthesis.py` to configure synthesis
without reprovisioning.
If Silver was already open when the project was configured for the first time,
quit it with `q` and reopen it: the running backend caches the ASIC configuration.
To reopen this example's **prepared** tools and saved session instead, use
`python3 -B scripts/silver.py open`.

## Where things live

| Location | Owner and purpose |
| --- | --- |
| [`ip/controlled_fifo/`](ip/controlled_fifo/) | FIFO RTL, independent model, stimulus, Cyclesim verification, and simulation provider |
| [`asics/fifo_demo/`](asics/fifo_demo/) | TT wrapper, ASIC project/flows, CLI, whole-wrapper verification and bundle replay |
| [`asics/program_memory/`](asics/program_memory/README.md) | Program-memory SRAM project, behavioral verification, and physical qualification harness |
| [`asics/sram_budget/`](asics/sram_budget/README.md) | Three identical RAM requests competing for a project-level SRAM instance budget |
| [`tooling_acceptance/timing/`](tooling_acceptance/timing/) | Five-register timing fixture and basic/named-flow/physical API qualification |
| [`tooling_acceptance/variants/`](tooling_acceptance/variants/README.md) | Parameterized memory constructor and conformance qualification |
| [`tooling_acceptance/workloads/`](tooling_acceptance/workloads/) | Workload execution/result qualification |
| [`integration/workbench/`](integration/workbench/) | Composite simulation routing and Workbench integration/qualification |
| [`scripts/`](scripts/) | Dependency/bootstrap, CLI checks, and development-session entry points |
| [`acceptance/`](acceptance/README.md) | Retained historical evidence, snapshots and reproduction packages |
| [`docs/`](docs/) | Guides, migration plans, and historical handoffs/results |

**IP owns its RTL and verification. ASICs own their tops and system verification.**
Root `verif/` is reserved for genuinely shared verification components when needed;
it is not a bucket for design-specific checks. See the
[ownership and storage guide](docs/repository_layout.md) for details.

## Build and verify

Use an already installed compatible `hardcaml_asic` provider. The development
dependency workflow is exposed by `python3 scripts/asic_dependency.py --help`.
Refresh/install is an explicit separate action; ordinary builds do not provision
EDA tools. Building the native simulation adapter additionally requires the Silver
provider SDK (`hardcaml_workbench_provider`).

For an existing prepared installation, `python3 -B scripts/silver.py configure-dune`
sets up checkout-local Dune library discovery once. Then `dune build .` works in
new shells using that compiler switch; there is no `OCAMLPATH` export to repeat.
Rerun the configuration if you deliberately change switches or move the checkout.

`asic-dependency.json` selects committed provider
`4b6bb60562c0133db9e3ccc6b183736e5658a3f0` for explicit **recorded** refreshes.
See [dependency selection and validation](docs/dependency_commands.md#current-recorded-dependency).
Changing this record does not upgrade an installed generation or the Workbench
selection; those continue to use their existing receipts and executable paths.

```sh
# With the example's ASIC dependency and Silver SDK already prepared:
dune build -j6 .
dune build -j6 asics/fifo_demo/cli/project.exe
dune runtest -j6 ip/controlled_fifo/verif/cyclesim
dune build -j6 @@asics/fifo_demo/verif/runtest
dune runtest -j6 asics/program_memory/verif
dune runtest -j6 tooling_acceptance/timing/fixture/verif
```

`@@DIR/runtest` is the exact nonrecursive alias. `dune runtest DIR` also includes
descendants; for example `dune runtest asics/fifo_demo/verif` includes bundle replay.
No directory needs to be named `test/` for Dune verification aliases to work.
Keep the total job allocation of concurrent commands at or below **20**.

**Editing `../hardcaml_asic` itself?** Run `./scripts/build_with_asic_checkout.sh`
from this checkout to build against those edits. It incrementally builds the
provider and the example in sequence. Neither step reinstalls the compiler,
Hardcaml or OxCaml. The example uses a separate build directory in this mode so
experimenting doesn't replace the project executable used by prepared Silver.
Use a development **refresh** only when you want a validated, installed snapshot
of the provider; it is not necessary on every source edit.

PDK-free bundle replay, including generated-Verilog simulation when Icarus is
available:

```sh
dune build -j6 @asics/fifo_demo/verif/bundle/acceptance-strict
python3 -B scripts/test_ownership_layout.py -v
```

The strict alias requires `iverilog` and `vvp`. Ordinary bundle verification reports
an explicit RTL skip if they are unavailable. Shared CLI/dependency checks remain
under `dune runtest -j6 scripts`.

## Project CLI

`chip list --json` lists the chips and variants built into the project executable.
The same `--chip ID` and `--variant ID` selectors apply to `flow list`, `describe`,
`plan`, `emit`, and `run`. Omitting both selects the original FIFO. Omitting only
the variant selects that chip's default.

| Chip | Variant | Named flow / default profile | Latest endpoint |
| --- | --- | --- | --- |
| `fifo_demo` (default) | `default` | `standard` / `balanced` | `signoff` |
| `program_memory` | `default` | `stock256-r0` / `qualification` | `timing` |
| `sram_budget` | `two_slot` (default), `three_slot` | `standard` / `balanced` | `synthesis` |

To inspect the three-slot design without starting any EDA tools:

```sh
dune build asics/fifo_demo/cli/project.exe
project=_build/default/asics/fifo_demo/cli/project.exe
"$project" chip list --json
"$project" flow plan --chip sram_budget --variant three_slot --endpoint synthesis --json > /tmp/budget-plan.json
jq '{project_name, variant: (.bundle_manifest | fromjson | .hardware_variant.assignments)}' /tmp/budget-plan.json
"$project" flow emit --chip sram_budget --variant three_slot --endpoint synthesis \
  --expected-plan-identity "$(jq -r .plan_identity /tmp/budget-plan.json)" --json
```

The two-slot bundle implements `bank2` with flops; the three-slot bundle maps
all three banks to stock SRAM. Their bundles and plan identities differ. Building
the multi-chip CLI requires the `hardcaml_asic` macro-limit API and schema-1
named synthesis planner; running a budget plan requires `sram_synthesis1` on
the execution provider. See [the SRAM budget example](asics/sram_budget/README.md)
for behavioral replay and setup against the sibling provider checkout.

```sh
dune exec -j6 asics/fifo_demo/cli/project.exe -- describe --json
dune exec -j6 asics/fifo_demo/cli/project.exe -- flow list --json
dune exec -j6 asics/fifo_demo/cli/project.exe -- flow plan \
  --flow standard --profile balanced --endpoint synthesis --json
```

The FIFO flow catalog supplies `standard` with `balanced` and `synth_delay`
profiles. Planning/emission does not launch physical EDA. Physical execution
remains an explicit request with a selected provider/toolchain and expected plan
identity. The source root is still the repository root containing `dune-project`
and `asic-dependency.json`, not the nested ASIC directory.

The FIFO is 16×8, register-backed, with synchronous active-high clear and a
registered pop response. See its [public interface](ip/controlled_fifo/rtl/controlled_fifo.mli)
for behavior and its [ASIC declaration](asics/fifo_demo/project/project.ml) for
target, timing, source inventory, and pin assignments.

For SRAM selection/operations and retained physical evidence, start with
[`asics/program_memory/README.md`](asics/program_memory/README.md).

## Silver and local storage

On a prepared and published checkout, run `python3 -B scripts/silver.py open`
to use Silver in one terminal. Quitting stops that session's daemon. See
[Everyday Silver](docs/workbench_main.md) for setup and persistent-server mode.

The supported Workbench loader currently discovers the three root companion files:

* `hardcaml-workbench-preparation.sexp`: build current source and emit its bundle.
* `hardcaml-workbench-asic.sexp`: selected project/provider executables, physical
  toolchain, result locations, and execution budget.
* `hardcaml-workbench-simulation.sexp`: selected simulation provider and budgets.

The preparation build target now names `asics/fifo_demo/cli/project.exe`. The
ASIC/simulation companions retain their existing pinned executables; moving source
does not rebuild or upgrade those selections.

The intended unified entry point is `.workbench/project.sexp`, but it requires a
coordinated Workbench loader change. Current companion files remain operational.
See the [continuation handoff](docs/migration_plans/workbench_continuation.md)
before creating or resuming a development session. Existing copied projects keep
their original layout; the new setup uses an explicit new `--store`.

Local storage roles:

* `.dev/`: installed development dependencies, captured provider generations, and
  setup bookkeeping; older experiments/results also remain here historically.
* `_flow_tools/`: provisioned runtime, PDK and tool collateral.
* `_flow_results/`: default generated bundles and execution evidence.
* `_build*/`: disposable Dune build trees, ignored by Git.

## Migration and historical documentation

The [migration plan and execution record](docs/migration_plans/ownership_layout.md)
contains scope, policies, verification, and follow-up work. The
[layout guide](docs/repository_layout.md) maps old paths to current owners.

Older `docs/pt7*`, `docs/pt8*`, and acceptance snapshots describe the paths and
identities that actually ran. The [archived root README](docs/archive/controlled_fifo_legacy_readme.md)
preserves the prior detailed usage/history; use the current layout map when
adapting its commands. Historical run evidence is not rewritten by source moves.
