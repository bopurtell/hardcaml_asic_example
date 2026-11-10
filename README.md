# Hardcaml ASIC development examples

Hardware projects and external-consumer qualification for `hardcaml_asic` and
Hardcaml Workbench. The original design is a controlled FIFO ASIC; the repository
also includes a program-memory SRAM ASIC and small tool-qualification fixtures.

## Where things live

| Location | Owner and purpose |
| --- | --- |
| [`ip/controlled_fifo/`](ip/controlled_fifo/) | FIFO RTL, independent model, stimulus, Cyclesim verification, and simulation provider |
| [`asics/fifo_demo/`](asics/fifo_demo/) | TT wrapper, ASIC project/flows, CLI, whole-wrapper verification and bundle replay |
| [`asics/program_memory/`](asics/program_memory/README.md) | Program-memory SRAM project, behavioral verification, and physical qualification harness |
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
EDA tools. Activate the selected provider in the shell that runs Dune. Building
the native simulation adapter additionally requires `hardcaml_workbench_provider`.

```sh
# After selecting and activating a compatible installed dependency:
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

## Workbench and local storage

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
