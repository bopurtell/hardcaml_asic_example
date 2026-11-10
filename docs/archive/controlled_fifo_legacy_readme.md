# Controlled FIFO ASIC specimen — historical root README

This is the root README before the 2026-11-10 ownership-layout migration. Its
commands and relative links describe the old root layout, not this archive
directory. For current usage see [the root README](../../README.md), the
[ownership guide](../repository_layout.md), and the
[migration record](../migration_plans/ownership_layout.md).

## Headless resource preparation (PT4)

The project-owned CLI now exposes `prepare`, `preview`, and `resources`, backed
directly by the public ASIC preparation APIs. See
[resource preparation](docs/resource_preparation.md) for isolated installation,
memory/FIFO commands, historical inspection and PDK/EDA-free acceptance.
`prepare` allocates durable operation evidence; `preview` computes the current
implementation preparation without publication; `resources` is a pure inventory
view with explicit `--simulation` support. FIFO succeeds with zero registered
resources. These are declaration/elaboration facts, not physical results.

An independent Dune project containing a fixed Hardcaml FIFO core, a consumer-owned
Tiny Tapeout wrapper, a shared Project declaration and CLI, repeatable
bundle acceptance, and PDK-free Cyclesim and generated-Verilog tests. This is a
**development specimen with an explicit consumer dependency record**.
It uses `core`, `hardcaml`, `ppx_jane`, `ppx_hardcaml`, `yojson`, and a selectable
development build of `hardcaml_asic` exposing the hardened `Resolved_flow.mli` and
the shared `Project.source_inputs`, `describe`, `emit_bundle`, and
`emit_bundle_to_store` API, `Bundle.publish`, `Flow_spec`, `Methodology_plan.prepare`,
and flow CLI contract **4** with **`namedflow1: true`** for named flows and installer
validation. Legacy Classic dispatch accepts exactly integer contracts **2, 3 or 4**;
the legacy explicit-stage `--endpoint` route requires **4**. Unknown versions fail
before bundle emission. Older closeouts below describe historical installations.
The project declares Dune language 3.17 and has been built with Dune 3.24.2 and
OCaml 5.2.0+ox. The record is not an opam pin. The installed
Hardcaml interfaces under `~/.opam/5.2.0+ox/lib/hardcaml/` are the API authority.

The generic `lib/`, `test_support/`, and `test/` stanzas remain independent of the
ASIC library. ASIC integration lives in `asic/`, `bin/`, `asic_test/`, and
`acceptance/`. Building,
simulation and resolution need no PDK, Workbench, or physical EDA. The emitter
only renders/writes a bundle; it never provisions dependencies or runs a flow.

Authored flow definitions are **project-owned**. This example currently registers
one flow, `standard`, in `asic/flow_catalog.ml`, with `balanced` and `synth_delay`
profiles in `asic/flow_profiles.ml`. The preferred future organization for several
definitions is a per-project `asic/flows/` directory with explicit catalog
registration. `hardcaml_asic` owns the types/execution machinery and may later
supply reusable standard presets. See the
[ownership, source layout and generated storage decision](../hardcaml_asic/docs/development/project-flow-catalog.md#per-project-source-layout-and-library-presets).

## Fixed core contract

The [registered 256×16 program-memory testbed](memory/README.md) is the ongoing
production-style SRAM acceptance design. It uses public APIs with explicit
flop/Exact selection, independent vendor-functional-model replay and deterministic
bundle checks. The CLI requires `--operation synthesis|hardening` as well as explicit
selection. Exact synthesis retains schema 1 and `(42,81)` R0; the new Hardening
declaration uses the explicit `(40,81)` candidate with unchanged latency and staging
registers. **P4 physical acceptance passed**: public full run, all-corner extracted
timing/electrical checks, real-GDS/physical policy checks, abstract macro-boundary
LVS with schematic CDL, external TT precheck and zero-delay final-gate replay.
The stock SRAM and 16 staging flip-flops are unchanged. Timed SRAM/SDF conformance,
internal-device LVS and IR/EM remain outside this accepted scope. See the
[physical evidence and practical verification commands](memory/PHYSICAL.md) and
[portable snapshot](acceptance/sram/README.md). Its emitted
bundle route uses the installed public provider, isolated `.dev/asic-sram` dependencies
and `_build_sram` builds at no more than six jobs. The FIFO commands below retain
their existing entry point.

For the standalone standard-library public-protocol client, frozen-prefix build,
direct named-flow commands, reconnect and provider reference handoff, see
[headless named flows](docs/headless_flow.md).

`lib/controlled_fifo.mli` is the public contract; `Controlled_fifo.create` accepts
a typed `Signal.t I.t` and returns a typed `Signal.t O.t`.

* Capacity: **16 words of 8 bits**, held in individual registers, not
  `Single_port_ram` or another memory primitive.
* Addressing: two 4-bit circular pointers; occupancy: 5 bits, ranging from 0 to 16.
* Inputs: `clock`, synchronous active-high `clear`, `enable`, `push`, `pop`, and
  8-bit `push_data`.
* Outputs: registered 8-bit `data_out` and 1-bit `data_valid`; combinational
  `push_accept`, `pop_accept`, `occupancy`, `full`, and `empty`.

At a rising edge, using **pre-edge** occupancy `count`:

```text
active      = enable && !clear
pop_accept  = active && pop && count > 0
push_accept = active && push && (count < 16 || pop_accept)
```

`clear` dominates all other inputs, including disabled operation: its edge zeros
both pointers, count, response data, and response valid. Stored words need not
reset. Apply a clear edge before use; power-up register values are unspecified.
While clear is asserted **before** that edge, both accepts are low but occupancy
and flags still describe the existing queue.

| Pre-edge state and requests (enabled, not clearing) | Behavior |
| --- | --- |
| Empty, pop only | Reject pop; hold response data, clear response valid |
| Empty, push + pop | Accept push only; no bypass to the response |
| Full, push only | Reject push |
| Full, push + pop | Accept both; return the **old head** before replacing its slot |
| Nonempty/nonfull, push + pop | Accept both; preserve occupancy and FIFO order |

Every accepted pop registers the old head into `data_out`. Every non-clear edge
sets `data_valid` to that edge's `pop_accept`. A disabled or no-accepted-pop edge
clears valid and holds response data; disabled edges also hold the entire queue.
`data_valid` is a response to the last edge, **not** a head-visible valid signal.
Consecutive pops may keep it high. `full` and `empty` depend only on occupancy.

## Build and run

### Project-owned FIFO simulation (FS2)

The standalone [FIFO simulation provider](simulation/README.md) exposes the real
directed and seeded Cyclesim tests, native VCD/checker reports, full uint64 seeds,
and an explicit checker-only mismatch mode. Only its native `test_provider.exe`
adapter links the Workbench provider library; tests remain standalone. Its
conservative installer explicitly builds the adapter and simulator at up to six
jobs, copies those two executables into persistent `.dev/` storage,
and adopts the separate Workbench simulation companion config. Discovery and
runtime never build or run physical tools. Ordinary CLI/Dune tests remain available.

### Project-owned named flows: discover, preview, then run

`asic/flow_catalog.{ml,mli}` and `asic/flow_profiles.{ml,mli}` are the checked,
project-owned declarations, exported by `Fifo_asic.Flow_catalog` and
`Fifo_asic.Flow_profiles`. Flow **`standard`** declares fresh LibreLane classic
prefixes, default profile **`balanced`**, and two explicit profiles:

| Profile | `SYNTH_STRATEGY` | `SYNTH_ABC_BUFFERING` |
| --- | --- | --- |
| `balanced` | `AREA 0` | `false` |
| `synth_delay` | `DELAY 1` | `false` |

```sh
# Build with a compatible installed provider selected in OCAMLPATH.
dune build -j6 bin/project.exe
PROJECT="$PWD/_build/default/bin/project.exe"
"$PROJECT" flow list --json
"$PROJECT" flow describe --flow standard --json

# Read-only preview: an endpoint is REQUIRED; this never defaults to signoff.
"$PROJECT" flow plan --source-root "$PWD" --flow standard --profile synth_delay \
  --endpoint synthesis --json > /tmp/fifo-plan.json
IDENTITY=$(python3 -c 'import json; print(json.load(open("/tmp/fifo-plan.json"))["plan_identity"])')

# EDA-less publication of this selected plan's bundle (no installed executable/tools needed):
"$PROJECT" flow emit --source-root "$PWD" --flow standard --profile synth_delay \
  --endpoint synthesis --expected-plan-identity "$IDENTITY" \
  --results-root /tmp/fifo-emitted-results --json

# Explicit implementation request, using existing provisioned tools:
"$PROJECT" flow run --source-root "$PWD" --flow standard --profile synth_delay \
  --endpoint synthesis --expected-plan-identity "$IDENTITY" \
  --provider /absolute/installed/prefix/bin/hardcaml-asic-flow \
  --toolchain "$PWD/_flow_tools" --json
```

Repeat exactly the preview's selection, endpoint, and `--set` arguments for emit or run.
Supported overrides are only `--set 'SYNTH_STRATEGY=DELAY 1'` and
`--set SYNTH_ABC_BUFFERING=true` (or other exact provider enum/boolean values).
The provider's typed `Parameter` API validates them; unknown keys, duplicates,
noncanonical enums, string/numeric booleans and profile-without-flow fail.
No selection uses the catalog's declared default pair; explicit `--flow standard`
without a profile uses that flow's declared default. Unknown IDs never fall back.

List/describe emit the versioned provider `hardcaml-asic.flow-list` /
`hardcaml-asic.flow-describe` wires without root discovery, Git, provider lookup,
elaboration or tools. Plan emits `hardcaml-asic.methodology-plan` v1 JSON (pretty
by default, compact with `--json`), including the frozen declaration, effective
settings and overridden provenance, exact configuration/manifest, bundle identity,
methodology hash and plan identity. It reads source/Git but creates no output
directories and performs no tool probes. All four declaration files are explicit
`Project.source_inputs` and are also passed to prepare as `catalog_inputs`.

`flow emit` calls `Methodology_plan.prepare` then `Bundle.publish`, retaining the
selected flow/profile and all override provenance inside the returned plan. It accepts
the same selection/root options as plan, plus `--results-root` (default
`SOURCE/_flow_results`) and optional `--expected-plan-identity`. Invalid selections,
overrides or identity mismatches fail before publication. It never checks or launches
a provider/tool and allocates no workspace, launchspec or execution attempt.
Provider/tool routing options are rejected; `TOOLCHAIN` is irrelevant.

The output is one JSON object (pretty by default, compact with `--json`):

```text
{
  "schema_version": 1,
  "kind": "bundle_emission",
  "bundle_identity": "<bundle SHA-256>",
  "plan_identity": "<plan SHA-256>",
  "output_dir": "<absolute RESULTS/bundles/IDENTITY path>",
  "reused": false,
  "plan": <Methodology_plan.to_yojson plan>
}
```

The manifest is `output_dir/manifest.json`. Repeating an unchanged request returns
the same plan, identities and output directory with `reused: true`.
Focused EDA-less tests read this checkout's source/Git without mutating it:

```sh
python3 -B scripts/test_flow_emit.py "$PROJECT" "$PWD"
```

#### Workbench source-bundle preparation (EDA-less)

**Resources inspector (2026-10-28):** the rebuilt app now has a Resources workspace.
Use **Space c c → Resources: Import retained resource evidence** with
`acceptance/resource-measurements/accepted-live-01/run` as an **absolute** path.
This reads the actual retained SRAM measurements without launching EDA. The owner
approved the local ASIC companion's provider upgrade to final PT.6 generation
`97b85a9e25e24615b758b97b21ca9697`; other settings and generation pointers remain
unchanged. See [current restart/import controls](../hardcaml_workbench/docs/resource_inspector.md).

**Unified fresh workflow (2026-10-27):** the current Workbench client/daemon runs
Elaboration before every fresh physical prefix. Checklist `r` stages inputs only;
`R` stages and launches. Elaboration-only stops after build/emission; Synthesis
and later endpoints consume that exact emitted bundle. See
[controls and restart instructions](../hardcaml_workbench/docs/unified_fresh_prefix_plan.md#delivery-and-user-verification).
The local ASIC companion's physical provider was explicitly upgraded to PT.5
generation `dd1ec9002cdc40f2936488cedd9eb0fe` because the old provider rejects the
new resource-snapshot manifest field. Existing generation pointers are unchanged.

`hardcaml-workbench-preparation.sexp` opts this checkout into Workbench's separate
source-bundle preparation API. It builds the actual `bin/project.exe` with Dune
`-j6` into `_build/default/bin/project.exe`, then runs `flow emit` with the selected
flow, profile, endpoint and overrides. The 600-second budget applies to each job.
Published bundles live in
`.dev/workbench-real-demo/preparation-results/bundles/`, alongside the pinned demo
store but separate from its physical `results/` evidence. The existing pinned ASIC
and simulation companion configurations keep their independent roles.

Start a preparation-capable Workbench daemon from the selected OCaml environment:

```sh
cd /home/wayne/devel/jane/hardcaml_asic_example
. .dev/asic-pt6/generations/97b85a9e25e24615b758b97b21ca9697/activate.sh
# Needed when inspecting the full workspace, which includes the simulation adapter:
export OCAMLPATH="$OCAMLPATH:$PWD/.dev/workbench-provider-sdk/lib"
export DUNEJOBS=6 OPAMJOBS=6 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
mkdir -p /absolute/private/discovery
/home/wayne/devel/jane/hardcaml_workbench/scripts/with-switch.sh \
  /absolute/path/to/preparation-capable-daemon --port 0 \
  --discovery-dir /absolute/private/discovery --state-dir /absolute/private/state
```

Connect to that daemon with project environment `inherited` so the activated
`OCAMLPATH` reaches its source-build child. The exact final `asic-pt6` generation
installation supplies both `hardcaml_asic` and `hardcaml_asic.execution`; no EDA
toolchain is needed. A daemon already running before activation does not acquire
the new shell environment. Opening this project alone does not submit preparation.

Use the palette's preparation-input selection for e.g. `standard / synth_delay`,
endpoint `synthesis`, and override `SYNTH_ABC_BUFFERING=true`. In the Overview
checklist, select Elaboration and use `r` to stage, or `R` to stage and launch. Inspect
the completed build/emission jobs, their logs and registered bundle artifacts;
repeat with unchanged source to verify bundle reuse. Elaboration Enter is read-only;
preparation cancellation uses `x`. The original standalone API's history and artifact handles are
daemon-session scoped, while published bundles persist on disk. Its backend API is
`POST /api/v1/preparation` with S-expression `Get`, `Prepare` (submission key,
selection, optional expected plan identity), or `Cancel` operations. Physical
execution remains an explicit action. The unified workflow uses ASIC RPC
`Stage_fresh`/`Launch_fresh`/`Cancel_workflow`, retaining durable workflow lineage;
fresh physical launch automatically includes source Elaboration.

Run calls `Methodology_plan.prepare` once, compares the required preview identity,
then negotiates exact integer CLI4 plus boolean `capabilities.namedflow1=true`
before publishing the **same prepared bundle**. Source, catalog, profile, request,
endpoint or Git context changes invalidate the preview before results creation or
provider dispatch. Run publishes a read-only, atomically no-replace plan launch file
under `RESULTS/launchspecs/`, then execs public provider `stages BUNDLE
--methodology-plan FILE --expected-plan-identity HASH` with explicit tool paths,
a fresh nonexistent workspace and its checkpoint store. `--bundle` and
`--checkpoint` are rejected. Results default to `SOURCE/_flow_results`; tool
precedence is `--toolchain` > nonempty `TOOLCHAIN` > `SOURCE/_flow_tools`, with
individual tool overrides. Relative paths retain caller-cwd semantics, executable
symlinks, spaces and symlink-parent/`..` traversal. `--provider PATH` is recommended
for configured clients; omission uses the human PATH fallback.

Named `flow run` alone accepts optional `--timeout SECONDS`: positive integer
seconds forwarded to public provider `stages --timeout`, per segment/publication.
Omission retains the provider's native 600-second default. For a full fresh
six-stage prefix, preview and run with `--endpoint signoff`, and use the recommended
`--timeout 3600` on run. This execution budget is outside the plan content hash;
changing it does not change profile, plan, bundle or snapshot identity within the
same source checkout. Editing declared source inputs naturally changes identity.

The [headless client](docs/headless_flow.md#client-and-reconnect) forwards optional
`--stage-timeout 3600` to that project option. Its separate `--timeout 7200` is the
recommended overall client budget for a full named flow; it is never forwarded.
Both are explicit recommendations, not new defaults (client default also remains
600 seconds). List/describe/plan and legacy project commands have no new option.

With `--json`, stdout is **unchanged provider JSONL**, beginning with native
allocation metadata linking the exact pending methodology snapshot. Retain that
attempt/stream and later checked reference; native operation receipts retain the
explicit request and immutable snapshot. The consumer adds no wrapper event or
second progress protocol. Observe with the installed provider's `observation`
commands below. A launchspec is launch input; the native retained snapshot is the
historical evidence. Legacy `describe`, `emit`, `preflight`, `run --stage` and
`run --endpoint` keep their existing routing and have no runtime profile state.

PDK-free test commands and private installed-provider validation are in
[dependency commands](docs/dependency_commands.md#named-flow-consumer-validation).

### Explicit-stage run and independent progress reader

After activating a contract-4 provider and using existing provisioned tools:

```sh
. .dev/asic/current/activate.sh
dune exec -j 20 bin/project.exe -- run --endpoint synthesis --json
# In another activated shell, use the early allocation receipt's attempt path:
hardcaml-asic-flow observation watch "$ATTEMPT" --json
# Save a complete updates envelope's stream_id/cursor, then reconnect:
hardcaml-asic-flow observation watch "$ATTEMPT" --stream-id "$STREAM_ID" --after "$CURSOR" --json
hardcaml-asic-flow observation inspect "$ATTEMPT" --json
```

`--endpoint synthesis|floorplan|placement|cts|routing|signoff` is mutually exclusive
with Classic `--stage synthesis|full`. The consumer emits/reuses the bundle and
execs installed provider `stages`; human output is default, and `--json` forwards
the provider's flushed allocation/terminal JSONL unchanged. Results use
`--results-root` or `SOURCE/_flow_results`; each invocation selects a unique,
nonexistent workspace there with `checkpoints` inside. The provider creates the
workspace and defaults the journal to results/`observations`, outside it.
`--bundle` bypasses emission. Tool precedence remains explicit `--toolchain`,
nonempty `TOOLCHAIN`, then `SOURCE/_flow_tools`, with per-tool overrides taking
precedence; defaults are `tt`, `pdk`, `.venv/bin/python` under that root.
`--native` and Classic-only `--runs` are rejected before emission for endpoints.
Recipes, resume and acceptance are separate provider operations; this route does
not finalize acceptance. Reader Ctrl-C stops only the reader; its exit 0 denotes
a recorded terminal outcome, so inspect `outcome.exit_code` for execution success.
See the [feature/evidence record](../hardcaml_asic/docs/development/flow-journal.md).

Run from this repository using an already available compiler, Dune, ocamlfind and
dependencies. First obtain and activate a compatible installed `hardcaml_asic`
provider: a normal opam installation (`opam install hardcaml_asic`, then
`eval "$(opam env)"`) suffices when it exposes the required Project API and provision
CLI. The finished consumer needs no ASIC library source checkout. The shared opam
package may currently expose an older API; for this development transition,
explicitly refresh a private installation from a selected checkout and activate it
before ordinary builds:

Refresh cannot activate the calling shell. Source the activation file in the
shell that will run Dune, and re-source after each refresh or opam environment
reset. For the observed stale `0.1.0` switch installation and exact recovery
commands, see [dependency commands](docs/dependency_commands.md).

```sh
python3 scripts/asic_dependency.py refresh --source /absolute/path/to/hardcaml_asic --mode development
. .dev/asic/current/activate.sh
python3 scripts/asic_dependency.py status --json
dune build @all -j 20
dune runtest . -j 20
dune build @acceptance-strict --force -j 20
dune exec -j 20 test/fifo_test.exe -- --directed
dune exec -j 20 test/fifo_test.exe -- --seed 42 --cycles 100000
dune exec -j 20 asic_test/wrapper_test.exe
dune exec -j 20 asic_test/resolution_test.exe
```

`db` can replace the plain build command if that local wrapper preserves the
activated environment. No sibling checkout path is assumed by the tool.

### Flow-tool bootstrap (separate from library development refresh)

After installing/activating the provider above, diagnose the selected flow-tool
root without changing it:

```sh
./bootstrap.sh --check --no-container
```

`bootstrap.sh` requires `hardcaml-asic-flow` on PATH and execs its `provision`
subcommand. The installed provider owns provisioning logic, locked versions and
option validation before provisioning. The wrapper neither installs nor refreshes
the provider. `./bootstrap.sh --help` forwards to provider help safely. Running
`./bootstrap.sh` with no arguments is an explicit request to provision.

Once host prerequisites are available, authorize actual provisioning by running:

```sh
./bootstrap.sh  # explicitly provisions missing managed runtime/collateral; uses network
# Optional external base override:
./bootstrap.sh --python /absolute/path/to/python3.11
```

Normal provisioning uses the installed provider's pinned **managed Python/Tcl**
base for new venvs, retained under `_flow_tools/python/`. Explicit `--python PATH`
selects an **external base**, not a flow run's venv interpreter. It must match
the locked minor (3.11) and supply `venv`, `ensurepip` and headless Tcl; an invalid
override fails before mutators, without fallback. Existing mismatched venvs need
explicit repair. The managed distribution needs no Python 3.11/Tcl system
packages; the host CLI still needs Python >= 3.9. OS libraries/certificates,
Docker images and Nix stores remain external.

Initial support is Linux glibc x86_64 >= 2.17, with kernel/filesystem support for
atomic no-replace `renameat2`; actual host acceptance used glibc 2.39/kernel 6.8.
Pinned archive size/SHA-256 are checked before extraction/execution, with safe
bounded extraction, staged/final probes and a final receipt. Retained generations
are never replaced. This is archive integrity/readiness, not P6.5 attestation.
See [pin, semantics and network-opt-in reproduction](../hardcaml_asic/docs/guides/consumer-installation.md#managed-python-integrity-and-initial-platform).

The earlier accepted provider generation was `f74ce0f369fd41b5b99811e0769dc756`
(CLI contract 2/default result storage); re-source activation in your shell.
The earlier runtime-policy acceptance used `caa4d18002274defb5eebb15e35a9042`.
Final 2026-10-12 `./bootstrap.sh --check`
including container exits **0**. The earlier five-gap result is historical.
Host flow Python remains **3.11**; the official LibreLane **3.1.0.dev3** image
may use supported Python **3.10..3.14** (observed **3.13.13**, Requires-Python >=3.10).
This needs **fresh bundle emission**, not editing an old bundle or a waiver.
See [simple emission/preflight commands and runtime policy](../hardcaml_asic/docs/guides/flow.md#runtime-policy-and-launch-binding)
and [current acceptance](../hardcaml_asic/docs/phase_plan.md#hostcontainer-runtime-policy-closeout).
The recorded consumer pin is unchanged pending owner adoption. The latest
[result-store closeout](../hardcaml_asic/docs/phase_plan.md#default-result-store-and-cli-2-closeout)
records the preserved 21-file bundle and readiness-only evidence. Final review
also preserves directory symlink-parent/`..` traversal; focused build and nine
routing tests passed. This source/docs change follows the stored acceptance
input snapshot. The acceptance bundle preserves its earlier dirty README; this update
does not change that stored input or identity. The historical observation probe
ran zero of eleven cases; neither its rerun nor a real ASIC flow has run in this
closeout. The old source 3.12 environment is unchanged.

Root precedence is a later explicit `--toolchain PATH`, then nonempty `TOOLCHAIN`,
then the absolute `_flow_tools/` directory beside `bootstrap.sh`. For example:

```sh
TOOLCHAIN="/storage/my flow tools" ./bootstrap.sh --check --no-container
./bootstrap.sh --toolchain "../shared flow tools" --check --no-container
```

The wrapper keeps the caller's working directory; explicit relative roots (including
`TOOLCHAIN`) retain that meaning. Only the default root is project-relative.
`/_flow_tools/` is ignored here; ignoring any overridden location is its owner's
policy. The provider puts `python/`, `tt/`, `pdk/`, LibreLane's `.venv/`, and the precheck
`.venv-precheck/` under the chosen root. `--check` changes nothing; `--offline` forbids fetching
(it is not a read-only mode); `--no-container` skips container-image provisioning
and checks, not TT/PDK/venv requirements. These and `--python` are forwarded without
consumer-side per-tool logic.

Project `describe` and `emit` below work independently of flow-tool provisioning.
The project CLI passes its selected tool and results roots to the installed provider:

```sh
dune exec bin/project.exe -- preflight
# Explicit expensive implementation request (not a bootstrap check):
dune exec bin/project.exe -- run --stage synthesis
```

Replace that root when using an override. Sourcing the provider-generated
`_flow_tools/toolchain-env.sh` is optional; the wrapper exports nothing to the calling shell,
and these commands do not rely on `TT` or `FLOW_PY`. LibreLane venv autoactivation
is unnecessary: shared-CLI orchestration uses a separate host Python and selects
the flow interpreters from `--toolchain`. Preflight/run are separate user actions,
not bootstrap tests or evidence of physical EDA success.

Recorder-only bootstrap tests (no provisioning, downloads or nested Dune):

```sh
python3 scripts/test_bootstrap.py
dune runtest scripts --force
```

### Consumer dependency setup

`asic-dependency.json` records schema, package, repository URL and full revision.
Normal **recorded** refresh reads committed bytes at that revision from the
explicit local repository, ignoring working edits. It never fetches. The initial
revision is `1714764859274f80a9f5ad207421a04601824e99`; before recording it, the
read-only command below checked its committed public interfaces for
`Elaborated_project`, `Resolved_flow` and `?simulation_project`, plus its flow
installation stanza. Real refresh/build evidence is recorded below; this command
alone checked source interfaces under the earlier setup contract (historical command):

```sh
python3 scripts/asic_dependency.py validate-source \
  --source /absolute/path/to/hardcaml_asic \
  --revision 1714764859274f80a9f5ad207421a04601824e99
```

**Project API transition:** the recorded `171476...` revision does not yet expose
`Project.source_inputs`, `describe`, `emit_bundle`, `emit_bundle_to_store`,
`Bundle.publish`/`Bundle.Publication`, and constructor `?source_inputs`.
The strengthened check now rejects that recorded API, including the historical
`validate-source` command above. Keep the record unchanged until its owner advances
it. During this transition, explicitly refresh **development** bytes with the new
API and re-activate. The recorded snapshot is still loaded for comparison, but
API requirements apply to the selected snapshot. `validate-source` remains a
read-only source check and reports `compiled: false` on success.

For this transition and local edits, explicitly select **development** mode:

```sh
python3 scripts/asic_dependency.py refresh --source /absolute/path/to/hardcaml_asic --mode development
. .dev/asic/current/activate.sh
python3 scripts/asic_dependency.py status --json
dune build @all
```

Development captures tracked files and relevant nonignored untracked files,
including deletions and safe internal file symlinks, excluding `.git`, `_build`,
`.toolchain`, `.dev`, Python caches and the selected store. Two capture comparisons
reject observed concurrent edits; this is not an atomic filesystem snapshot or a
clean-checkout claim. Builds use captured bytes in a private temporary directory.
Neither mode changes the baseline record, opam pins or shared source `_build`.
Missing dependencies/revisions and incompatible source fail with no provisioning.

The ignored `.dev/asic/` store contains `.owner`, `writer.lock`, `generations/<id>/`
and an atomically replaced `current` symlink. Each generation contains installed
`lib/`, `bin/hardcaml-asic-flow`, `receipt.json` and `activate.sh`. Installation uses
the final generation prefix; publication follows interface/runtime-file checks,
CLI `--help`, an exact ocamlfind resolution check and compilation of a tiny external
consumer using `Resolved_flow.t`, `Elaborated_project.t`, `Bundle.render`, and the
new Project constructor/inventory/description/emission/store-publication signatures
(including both optional emission arguments and publication fields), plus
a Dune executable link probe. Metadata pointing into the temporary capture is rejected.
The installed runtime must include `result_store.py`; `--version --json` must
advertise supported CLI contract 2 or 3. This protocol version is separate from package/source
version. Missing assets or incompatible APIs/CLI fail before selection publication.
The release build uses `-p` (which implies `--root .`) in the capture directory and
a relative `_build` directory so installed archive paths remain relocatable.
One writer holds a nonblocking store lock. Failures retain the previous selection;
old and failed generations are retained, with no automatic garbage collection.
An existing unowned store destination is rejected. Global `--store /absolute/path`
(before the subcommand) selects a fresh private store; source that store's
`current/activate.sh`. Global `--record PATH` selects another dependency record.
Symlinked store paths and colons/newlines are rejected.

**Re-source after every successful refresh.** Activation pins OCAMLPATH and PATH
to a specific generation, so an active shell stays on its prior generation until
reactivated. It removes known managed prefixes and preserves unrelated entries.
To explicitly retire the selected source's previous manual override, add
`--remove-source-build-override` to refresh; its exact
`SOURCE/_build/install/default/lib` path is recorded for removal on activation.
Without that flag, manual paths are preserved after the selected generation.
POSIX shell activation supports spaces and apostrophes in paths.

`status --json` is read-only and reports the published generation separately from
the caller's active-generation marker and OCAMLPATH, including an older active
generation, development override, captured differences from its observed base,
and baseline mismatch. Receipt facts describe refresh inputs, not today's checkout.
The snapshot checksum is **local bookkeeping, not P6.5 source stamping**; the CLI
reports unstamped in the validated installations. See the authoritative
[consumer dependency workflow](../hardcaml_asic/docs/development/consumer-dependency-workflow.md)
for scope.

PDK-free setup tests use injected build/install/compiler/CLI processes and
disposable Git fixtures with `Bundle test <bundle@test.invalid>` identities:

```sh
python3 scripts/test_asic_dependency.py
dune runtest scripts --force
```

All 18 setup tests also participate in ordinary `dune runtest`, using injected
processes without nested Dune calls. Real refresh runs its Dune consumer probe
before publication.

The strict alias requires both `iverilog` and `vvp` on PATH. Ordinary `runtest`
still runs bundle acceptance when either is absent, printing an explicit RTL
**SKIP**; it does not count that as RTL acceptance. Python 3 and Git are required
for the synthetic fixture. These commands use existing tools, without installing
dependencies. Both acceptance aliases consume Dune executable dependencies
directly and never invoke nested Dune builds.

### Source-breaking ASIC API migration

The public API now uses `Elaborated_project` (formerly `Build`) and
`Resolved_flow` (formerly `Resolved_build`). The resolved record field is
`.elaborated_project` (formerly `.build`), and `Bundle.render` accepts
`?simulation_project` (formerly `?simulation_build`). There are no compatibility
aliases: consumers must update source and recompile against the renamed provider.
This example uses the new names for both Implementation and Simulation elaboration.
The rename preserves persisted bundle keys, ordering and hashing; it does not
provide binary compatibility. Dependency selection is handled by the setup above.

The ordinary core test executable accepts either `--directed` or **both** `--seed INT`
and `--cycles NONNEGATIVE_INT`; there are no implicit random defaults.
`dune runtest` runs the directed suite and seed 20261012 with 20,000 traffic edges.
A regression adds one initial clear, enough pops to drain the remaining queue,
and one rejected pop, so reported edge counts exceed `--cycles`. Seeded traffic
uses a local PRNG and is reproducible for the same toolchain. It alternates
fill/drain bias, emphasizes boundary simultaneous requests, and includes clear
and disabled cycles. Final draining checks the remaining data order.

Successful runs report edges, accepted and rejected operations, clear/disabled
edges, and pre-edge visits to occupancies 0, 1, 15, and 16. Rejection totals
include requests suppressed by clear or disable. Failures include the suite/seed,
cycle, phase, field, expected/actual value, current labeled stimulus and expected
trace, and up to eight preceding traces (newest first).

### Directed coverage

* All four push/pop combinations at each occupancy 0, 1, 15, and 16, crossed
  with both clear values and both enable values: **64 independent probes**.
  Each probe primes a nonzero response, builds its queue, and drains afterward.
* Clear priority while disabled, full, and requesting both operations, including
  a full queue with a valid response from the preceding replacement.
* Overflow/underflow rejection, empty no-bypass, old-head full replacement,
  response hold and valid clearing across idle/disabled/rejected-pop edges.
* Three 1,024-edge simultaneous streams at occupancies 1, 15, and 16, with
  consecutive valid responses and order-checked drains.
* 64 fill/overflow/drain/underflow rounds, exercising both pointer wraps.

## Independent model and acceptance tests

`test_support/fifo_test_support.mli` exposes plain OCaml values and depends only
on Core, not Hardcaml or the DUT:

* `Stimulus.t` / `Stimulus.create`: edge inputs without a simulator clock port.
* `Snapshot.t`: occupancy/flags and registered response data/valid.
* `Model.initial`, `Model.snapshot`, `Model.step`: immutable list-based reference
  state and a pure transition returning next state, accepted push, accepted pop.
  It removes the old head first, then appends if there is room. It has no circular
  pointers and shares no RTL acceptance implementation.
* `Trace.of_stimuli`: turn labeled stimuli into expected before/after snapshots
  and edge accepts. Custom traces should start with a clear edge.
* `directed ()` and `regression ~seed ~cycles`: ready-to-replay expected traces.

`test/fifo_test.ml` is the separate Cyclesim adapter. It drives the stimulus,
calls `cycle_check` and `cycle_before_clock_edge`, and reads `Before` outputs to
check accepts and existing state. It then calls `cycle_at_clock_edge` and
`cycle_after_clock_edge`, and reads `After` outputs to check registered responses
and updated occupancy/flags. After-edge accepts refer to a future edge and are
not mistaken for the just-completed transaction. The first edge checks clear's
accept suppression and post-clear state without assuming power-up values.

`asic_test/wrapper_test.ml` replays those same directed and seeded traces through
the TT pins without duplicating the core acceptance rules. It checks every output
byte before/after edges, thus checking occupancy bit order, response data/valid,
zero low output bits and OE. Between edges it crosses enable/reset and toggles
ignored upper inputs, then unmasks the unchanged state. These probes distinguish
an immediate output mask from a synchronous queue reset. Upper inputs also vary
at actual edges. The directed cases inherit full replacement, empty no-bypass,
reset-while-disabled priority, overflow, underflow and pointer-wrap checks.

`asic_test/resolution_test.ml` uses public `Project.elaborate_for_flow` and a
separate `Project.elaborate ~mode:Simulation`. It checks exact top/ports, target,
clock, all I/O delay ranges, template setting values/reasons, generated settings,
24 pin descriptions, and empty resource inventories in both elaborated projects. It also
checks that a Simulation elaborated project is rejected by the implementation resolution
boundary. These tests read no PDK files and render no bundles.

## TT wrapper and pin map

`asic/tt_wrapper.ml` aliases `Tt_cmos5l.I` and `Tt_cmos5l.O`; the top is
**`tt_um_controlled_fifo`**. The exact ports are inputs `clk`, `ena`, `rst_n`
(one bit each), `ui_in[7:0]`, `uio_in[7:0]`, and outputs `uo_out[7:0]`,
`uio_out[7:0]`, `uio_oe[7:0]`.

| TT pins | Meaning |
| --- | --- |
| `ui_in[7:0]` | Push data, bit 0 LSB |
| `uio_in[0]` | Push request |
| `uio_in[1]` | Pop request |
| `uio_in[7:2]` | Ignored |
| `uo_out[7:0]` | Registered pop response, bit 0 LSB |
| `uio_out[1:0]` | Always zero; these pins remain inputs |
| `uio_out[2]` | Registered response valid |
| `uio_out[7:3]` | Occupancy 0–16, **pin 3 LSB** |

All 24 UI/UO/UIO pin descriptions are declared in `asic/project.ml`.
`clk` connects directly to the core clock, `ena` to enable, and `!rst_n` to
**synchronous** clear. Inputs and reset must be synchronous to `clk` and stable
across its rising edge. There is **no implicit reset synchronizer**. Apply a reset
edge before use, including when disabled. Queue reset takes effect only at that
edge, while the output mask is combinational: `uo_out` and `uio_out` are zero
whenever `!(ena && rst_n)`; `uio_oe` is `0xFC` iff `ena && rst_n`, else zero.
Releasing a reset pulse that contained no clock edge reveals the old queue and
response. Masking alone is not a queue clear. Consumers decode empty/full from
occupancy 0/16; the explicit core flags and accepts remain covered by core tests.

## ASIC analysis assumptions

The declaration selects **TT6x4 / IHP SG13 CMOS5L**, LibreLane **Hardening**, and
`Tt_cmos5l.overrides ()`. It explicitly selects default resource policy **Flops**.
The FIFO's ordinary registers are not registered `Single_port_ram` resources:
the resource inventory is intentionally empty, not an inventory of 128 RAM bits.

* One `clk`, **48 MHz**, period approximately **20.833333 ns**.
* Inputs `ui_in`, `uio_in`, `ena`, `rst_n`: **min 0 ns, max 1 ns**.
* Outputs `uo_out`, `uio_out`, `uio_oe`: **min 0 ns, max 2 ns**.

These are fixed **specimen analysis assumptions**, following the library example's
0/1 ns input and 0/2 ns output convention, with every nonclock port covered.
Explicit zero minimums allow earliest-change/hold analysis rather than omitting
minimum constraints. They are not measured board timing, a reset CDC solution,
or evidence of physical timing/area/DRC acceptance. The library supplies reference
target revisions and geometry; pure resolution checks their structure without
opening or verifying external files. Those target references do not pin this
consumer's OCaml dependencies; the explicit consumer record above selects the provider.

## Project entry point and standalone CLI

`Fifo_asic.project ()` returns the generic `Hardcaml_asic.Project.t` declaration.
The façade also retains `Fifo_asic.Tt_wrapper` for wrapper tests. Inventory lives
in `asic/project.ml` and is passed to the generic constructor.

The Dune executable has four subcommands. Human output is the default;
`--json` requests machine output and `--verbose` adds diagnostics on stderr:

```sh
dune exec bin/project.exe -- describe
dune exec bin/project.exe -- describe --json
dune exec bin/project.exe -- emit
dune exec bin/project.exe -- emit --json
dune exec bin/project.exe -- preflight --json
# Requires an explicit expensive implementation stage:
dune exec bin/project.exe -- run --stage synthesis
# Exact-output compatibility mode:
dune exec bin/project.exe -- emit \
  --source-root /absolute/path/to/consumer-source \
  --output-dir /absolute/path/to/new-or-empty-bundle --json
```

`describe` prints the shared `Hardcaml_asic.Project.describe` Sexp: local declaration
facts, **not a public Workbench provider schema**. Its local JSON shape is
`{"project_name":"controlled_fifo_specimen","declaration_sexp":"..."}`.
It does not elaborate, inspect
Git, create output directories, or run EDA. No arguments or invalid commands exit
2 with usage; `--help` exits 0. There is no expensive default or legacy CLI shim.

The built `_build/default/bin/project.exe` is also directly invocable with
the same subcommands. The source root supplies provenance and declared input bytes;
it does not rebuild the executable. Use an executable built from the matching
sources. The explicit root allows fixture-based acceptance to supply a
synthetic committed source checkout without altering the actual project checkout.

Root discovery walks upward from the caller's working directory to a directory
containing both `dune-project` and `asic-dependency.json`. Implicit emission then
validates all declared source inputs. Automatic discovery rejects generated
`_build`, `_flow_results`, and `.dev` trees, and callers outside the project must
supply `--project-root ROOT` or `--source-root ROOT`. These are root aliases;
both may be given only if their normalized absolute paths agree. No sibling
checkout, compiled source path, newest-bundle search or UI root state is used.
All user relative paths (also `TOOLCHAIN`) are normalized against the caller CWD;
provider dispatch preserves that CWD.

`--results-root` defaults to `<project-root>/_flow_results`. Default emission
calls the shared `Hardcaml_asic.Project.emit_bundle_to_store` into its `bundles/`
store. Complete objects live in hidden `bundles/.objects/<identity>.*` directories;
exclusive identity symlinks publish them at `bundles/<identity>`. Repeat emission
renders current inputs and reuses only exactly verified matching bytes and paths.
Corrupt or unexpected existing contents are refused without overwrite. Retain
published hidden objects: there is no automatic GC. This is bounded bundle reuse,
not a physical-result cache or run resume.

Explicit `--output-dir DIR` instead calls `Hardcaml_asic.Project.emit_bundle`
at that exact new/empty directory, retaining the compatibility behavior.
The shared API owns implementation resolution, default simulation elaboration,
rendering and writing. The library owns RTL/config/SDC/metadata/manifest emission and
provenance. Human success reports created/reused, path and identity. With `--json`,
success retains the previous two-field payload (scripts must now request the flag):

```json
{"identity":"<bundle SHA-256>","output_dir":"<requested path>"}
```

`preflight` and `run` accept `--bundle PATH`; otherwise they emit/select the
**current** project bundle without emitter output leaking into provider stdout.
They require `hardcaml-asic-flow` on PATH and check its CLI contract 2 or 3 metadata
before emission. There is no checkout fallback or automatic dependency refresh.
Dispatch uses executable/argv and replaces the consumer process, preserving
provider exit status and signals. Provider policy and report JSON remain shared.

Contract 3 also makes provider `stages`, all `observation` queries,
`checkpoint-inspect`, `finalize`, and `finalization-inspect` human-readable by
default. Parsing callers must pass `--json`; observed stages and finalize emit
allocation/terminal JSONL (parse each line). Observation queries and inspectors
return one complete object. Global, command-local and nested observation-query
flags work. Inspection is read-only; `checkpoint-inspect --restart-to cts` only
validates continuation, without running CTS. For example:

```sh
hardcaml-asic-flow observation inspect "$ATTEMPT"
hardcaml-asic-flow observation inspect "$ATTEMPT" --json
hardcaml-asic-flow checkpoint-inspect "$PLACEMENT" --restart-to cts
hardcaml-asic-flow checkpoint-inspect "$PLACEMENT" --restart-to cts --json
```

See [current activation and verification](docs/dependency_commands.md) and the
provider's [presentation closeout](../hardcaml_asic/docs/development/human-readable-flow-output.md).

Both forward absolute `--results-root` and `--toolchain`: explicit `--toolchain`
wins over nonempty `TOOLCHAIN`, then `<project-root>/_flow_tools` is the default.
`--python`, `--support-tools`, `--pdk-root`, `--native`, `--json` and `--verbose`
are forwarded when supplied. `preflight --output FILE` means the exact report
file with an existing parent, not a bundle output directory. Default preflight
writes a durable diagnostic operation receipt/report beneath
`_flow_results/operations/<UTC_shortid>/`; explicit output creates no additional
operation. This differs from read-only `bootstrap.sh --check` tool diagnostics.

`run` requires `--stage synthesis|full` before emission or dispatch; `--runs DIR`
overrides the default `<results-root>/runs`. Provider run allocates a fresh run
and performs its own fresh preflight before probes. The consumer does not add a
duplicate preflight, collect, postcheck or signoff. Completed implementation is
not physical acceptance. The layout is:

```text
_flow_results/
  bundles/<identity> -> .objects/<identity>.<unique>
  bundles/.objects/<identity>.<unique>/...
  operations/<UTC_shortid>/...   # default preflight receipt/report
  runs/<fresh-timestamp>/...     # implementation run and preflight
```

There is no project `execute`, `postcheck` or `inspect` yet. The full replay bench
requires `+trace` and is not a physical postcheck contract. Read-only report and
explicit collect remain installed-provider operations on existing runs; provider
`collect --json` writes normal results, legacy `collect --stdout` is read-only
JSON, and `report` is read-only.

Failures print the library diagnostic plus source-provenance guidance to stderr
and exit 1; missing CLI arguments exit 2. Bundle output must be new or empty;
existing files are not overwritten. A write failure may leave partial output.
Rendering requires a source checkout with at least one commit. The owner's checkout
satisfies that prerequisite; real acceptance verifies its current revision using
read-only Git inspection and preserves dirty/untracked input statuses. A revision
alone establishes neither a clean working tree nor a dependency pin. The emitter does not create a commit or
fabricate a revision to bypass the provenance requirement.

The explicit `Hardcaml_asic.Project.source_inputs` inventory has 15 paths:

```text
dune-project
asic-dependency.json
README.md
lib/dune
lib/controlled_fifo.ml
lib/controlled_fifo.mli
asic/dune
asic/tt_wrapper.ml
asic/tt_wrapper.mli
asic/project.ml
asic/project.mli
asic/fifo_asic.ml
asic/fifo_asic.mli
bin/dune
bin/project.ml
```

This covers all consumer generation inputs, including wrapper, declaration,
metadata, build stanzas and emitter. Tests/model are not generation inputs;
dependency libraries are not copied into this inventory. `asic-dependency.json`
captures the consumer's dependency expectation, not proof of linked library identity.
Local refresh receipts and setup scripts are not hardware generation inputs.

## Bundle and generated RTL acceptance

Slice 4 focused verification uses the provider's already built install tree via
temporary `OCAMLPATH=/absolute/provider/_build/install/default/lib`, because the
selected private consumer generation predates store publication. The routing
suite uses seven synthetic-source/recording-provider cases, including verified
reuse/corrupt refusal, current-source selection, root validation, overrides,
stdout purity, exit status and signal propagation. The dependency suite has 17
tests, including missing `result_store.py`, bad publication API and old CLI
refusal before publication. These do not run physical tools. Managed development
refresh, installed-provider real preflight and final real-checkout acceptance
are deferred to the next slice after this README settles; the slice 3 evidence
below remains historical.

For acceptance against the **actual checkout**, activate and build first, then use
a fresh ignored work directory (the following path is used for slice 3 evidence;
choose another fresh name when rerunning):

```sh
. .dev/asic/current/activate.sh
dune build @all
python3 acceptance/check_bundle.py \
  --emitter _build/default/bin/project.exe \
  --exporter _build/default/acceptance/export_trace.exe \
  --source-root /home/wayne/devel/jane/hardcaml_asic_example \
  --bench acceptance/replay.v --require-rtl --real-checkout \
  --work-dir .dev/emitter-checks/project-entrypoint-slice3
```

This mode performs only read-only Git inspection. It emits `first/` and `second/`,
compares complete trees byte-for-byte, checks every manifest file/input hash and
copied byte, and checks each input's actual Git status and the checkout revision.
`evidence.json` preserves those observations, including whole-checkout status.
The shared trace exporter and replay bench independently compile and simulate the
actual first bundle's synthesis and simulation RTL, including negative-oracle
checks. Traces and both compiled `.vvp` files remain alongside the bundles.

`acceptance/check_bundle.py` obtains the actual `Hardcaml_asic.Project.source_inputs` list
from `acceptance/export_trace.exe`, copies just those files into a temporary
source tree, and initializes a **synthetic local repository** there. It never
copies `.git` or `_build` and never commits the consumer checkout. The only fixture
commit has author and committer **`Bundle test <bundle@test.invalid>`**, message
**`baseline`**, and fixed dates. The script enforces identities in the subprocess
environment and per-command configuration, then verifies the recorded identities,
message, and absence of remotes. Inherited Git selectors are removed; system and
shared user configuration are excluded, and signing/hooks are controlled by
temporary test-local configuration. The fixture is removed after the test.

For before/after API compatibility, optionally supply a saved pre-migration
executable (kept outside the source tree) after verifying its trusted hash:

```sh
python3 acceptance/check_bundle.py \
  --emitter _build/default/bin/project.exe \
  --exporter _build/default/acceptance/export_trace.exe \
  --source-root . --bench acceptance/replay.v --require-rtl \
  --baseline-emitter /absolute/path/to/saved-pre-migration.exe \
  --baseline-source-root /absolute/path/to/saved-consumer-source \
  --baseline-inputs /absolute/path/to/saved-inputs.txt
```

The baseline uses its old flags; the current executable uses `emit --json`.
Saved standalone binaries are the default; for a saved project-v1 binary select
`--baseline-cli project-v1` (uses `emit` without the new flag). The fixture stages the union of both
inventories at one synthetic revision, restoring **only old-only paths** from the
saved source snapshot. Shared paths keep current bytes. Each bundle is inspected
against its own inventory. Comparison requires byte-identical synthesis RTL,
simulation RTL, config, SDC and info, and equal nonprovenance manifest facts.
Different inventories naturally have different manifests/identities. Repeated new
emission still requires whole-tree equality. For an old-CLI baseline with the same
inventory, omit both baseline source/inventory options; whole-bundle equality is
then also required. Ordinary and strict aliases need no baseline executable.

Bundle checks cover:

* Two independent emissions with identical relative paths and bytes, including
  the manifest; JSON response identity/output path agrees with the manifest.
* Exact emitted inventory, every emitted SHA-256, and each declared input's
  copied bytes/hash and tracked status.
* Exact top, TT6x4/CMOS5L target, Hardening operation, separate synthesis and
  simulation source lists, and intentionally empty registered-resource lists.
* Manifest/config agreement, all resolved settings (including the bundle-relative
  floorplan rewrite), generated source/SDC paths, 48 MHz clock and every min/max
  I/O delay, plus TT metadata and 24 pin descriptions.
* Tracked README and OCaml source comment edits change identity and are preserved
  byte-for-byte in copied inputs. The built emitter is unchanged; these probes
  test source provenance, not rebuilding modified logic. Emitted bundles are
  never hand-edited.
* Five actual nonzero failure cases: unborn source with absent/existing output,
  nonempty output refusal, and missing source with absent/existing output.
  Existing output bytes remain intact, and failed renders create no new output.

`acceptance/export_trace.ml` exports expected before/after state directly from
the existing pure list-based `Fifo_test_support`; Python and Verilog contain no
second FIFO model. `acceptance/replay.v` replays the full **7,330-edge directed
trace**, followed by **seed 20261012, 4,096 traffic cycles** plus reset/drain:
**11,429 total edges per source set** with the current toolchain. Icarus compiles
the synthesis source set and simulation source set **separately**, selecting the
same testbench top for both.

The bench checks registered response data/valid, occupancy pin ordering, low output
bits and OE before/after edges. Between edges it crosses reset/enable masks and
toggles ignored upper inputs, then checks that unmasking reveals unchanged state.
Directed coverage includes old-head full replacement, empty no-bypass, disabled
edges, synchronous reset priority, overflow/underflow and pointer wraps. Comparisons
use case-inequality to reject X values, except unspecified pre-initial-reset state.
Failures exit nonzero with trace index, phase, inputs, expected and actual output
bytes. Each compiled source set must also **reject a deliberately corrupted
expected response** at trace index zero; a successful negative run fails acceptance.

### Evidence and remaining limits

On 2026-10-12, slice 3 ran the normal managed refresh:

```sh
python3 scripts/asic_dependency.py refresh \
  --source /home/wayne/devel/jane/hardcaml_asic --mode development
```

It published `.dev/asic/generations/69a5db1892234a28b0884442ab0291f1`, with
`receipt.json` and `activate.sh` in that prefix. The observed provider base was
`82c0d7f7fbaa2d1796427de1037644946ceb2294`; captured snapshot SHA-256 was
`64b10f0e17e348105053f2f0c095d97bf2a8397a096b135b603c45ca43b2b6ce`.
Captured bytes differ from both the observed base and recorded snapshot.
The existing removal of the provider's manual `_build/install/default/lib`
override was carried forward. The refresh compiled the installed API and Dune
probes before publication.

After activation in a child shell, `ocamlfind query hardcaml_asic` and
`command -v hardcaml-asic-flow` selected that same private generation. Status
reported `active_is_published` and `active_library_path_is_first` true, with the
development/dirty/base-mismatch flags true. Running the same refresh command
with `--mode recorded` rejected the actual unchanged `171476...` record with
`incompatible Project.create API`, preserving the successful development selection.

Plain `dune build @all`, `dune runtest --force`,
`dune build @acceptance-strict --force`, and `dune exec bin/project.exe -- describe`
passed in the activated shell without a manual OCAMLPATH override. Core and wrapper
Cyclesim each passed 7,330 directed plus 20,017 seeded/reset/drain edges. Public
resolution, all 16 setup tests, and CLI purity/usage checks passed. Each generated
RTL source set passed 11,429 edges and rejected the negative oracle. Fixture bundle
checks passed with repeat whole-tree equality, two tracked edits and five failure cases.

The saved pre-migration executable at
`/tmp/opencode/project-api-baseline-k9wvcigz/emit_bundle.exe` was verified before use:
SHA-256 `739024f92ae88bf45d48e63ed67673b83a73c5fb4c5078db16efe8bbdcfe7cc1`.
The optional baseline command above passed with its sibling `consumer-source/`
and `inputs.txt`. All five generated artifacts and nonprovenance manifest facts
were equal; inventories differ (13 old inputs, 15 new), so this is not old/new
whole-bundle equality. Both RTL source sets also passed strict replay and negative
oracles. Real-checkout evidence uses the command and preserved directory above;
its `evidence.json` records actual dirty/untracked status rather than a clean-tree claim.
This README is a declared input: later documentation edits legitimately change
future bundle identity. The preserved slice 3 bundles and copied README describe
their historical snapshot, not today's source bytes; they are not rewritten.

The selected installed CLI's `hardcaml-asic-flow --version --json` reports package `0.1.0`,
`source.stamped=false`, state `unknown`, and null revision, inventory digest and
library-artifact match. Receipts are local selection evidence, not generator stamps.

This is deterministic functional RTL simulation, not a gate-level timing test or
formal proof. Bench delays allow combinational settling and do not model board
setup/hold or metastability; the 48 MHz and I/O constraints are analysis assumptions.
No synthesis, physical EDA, PDK validation, area, timing closure or DRC acceptance
has been run. Synthetic fixture revisions establish test provenance only, not a
release revision for this consumer. The owner's initial commit satisfies the
commit prerequisite for normal emission. The consumer dependency record selects
a provider revision; this acceptance does not establish reproducibility across
provider/toolchain revisions or authoritative P6.5 linked-artifact identity.
