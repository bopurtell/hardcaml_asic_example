# Ownership-oriented repository migration

Date: 2026-11-10

Status: source-layout migration implemented and verified. Unified Workbench
configuration remains a coordinated follow-up. This plan was published before
implementation; actual checks and continuation instructions are recorded below.

## Goal and ownership rules

Make the repository understandable as hardware projects plus independent tooling
qualification, rather than a flat collection of development-phase directories.

* An IP owns its RTL, reference models, stimulus, and verification. Reuse by a
  parent ASIC does not transfer ownership to a global verification directory.
* An ASIC owns its top/wrapper, project and flow declarations, CLI, system-level
  verification, and authored physical intent. Its environment may instantiate
  reusable host, bus, PHY, or wire-level verification components.
* Root `verif/` is reserved for genuinely reusable verification infrastructure,
  not a collection of every design's tests. Do not create empty agent frameworks.
* Tool API/protocol acceptance belongs to `tooling_acceptance/`, even when its DUT
  is an example ASIC. Tiny qualification fixtures belong with that acceptance.
* Keep library/module names and hardware behavior stable where possible. Dune
  directory names are not semantic: `verif/` still uses the normal `runtest` alias.
* Active source paths change; historical captured input bytes, receipts, source
  snapshots, archives, and result identities remain descriptions of past runs.

## Intended source layout

```text
ip/controlled_fifo/
  rtl/                         controlled_fifo library
  verif/
    support/                   IP-owned reference model and traffic
    cyclesim/                  standalone core checks
    simulation/                FIFO simulation provider and simulator
asics/fifo_demo/
  rtl/                         TT wrapper
  project/                     ASIC declaration, catalog, profiles, facade
  cli/                         project executable and stage recipe client
  verif/                       wrapper and declaration checks; RTL bundle replay
asics/program_memory/          standalone SRAM ASIC specimen
tooling_acceptance/
  timing/
    fixture/                   shared five-register qualification hardware
    basic/                     basic timing-intent project and checks
    named_flow/                named-flow integration of that fixture
    physical/                  physical timing qualification and harness
  variants/                    parameterized memory API/conformance specimen
  workloads/                   workload API/conformance clients
  ...                          feature-specific acceptance drivers
integration/workbench/         composite provider and Workbench-specific helpers
scripts/                       repository CLI/dependency/bootstrap entry points
verif/                         shared verification utilities when justified
acceptance/                    deliberately retained historical evidence
docs/migration_plans/          architectural migrations and continuation records
.workbench/                    future Workbench project configuration entry point
.dev/                          local installed dependencies/helper bookkeeping
_flow_tools/                   provisioned EDA runtime/PDK/collateral
_flow_results/                 generated bundles and execution evidence
```

The program-memory specimen currently combines core, TT adapter, and declaration
in one module. Preserve that behavior during relocation; identify its ownership
clearly, and avoid a gratuitous hardware/API rewrite merely to split the file.
Shared Python protocol utilities should have one owner and explicit import paths.

## Migration workstreams

1. **Hardware ownership:** relocate FIFO RTL/model/core checks, ASIC wrapper,
   declaration, CLI and ASIC checks. Relocate the program-memory specimen and its
   verification with consistent source inventories and Dune relationships.
2. **Tool qualification:** group the timing fixture/basic/named/physical routes;
   relocate variant and workload clients and phase-specific acceptance drivers.
   Update active paths, sibling imports, source inventories, and fixture builders.
3. **Repository/Workbench integration:** update shared scripts, source-copy closure,
   simulator installation, provider imports, test targets, and fresh-session setup.
   Existing captured development projects must not be refreshed or merged silently.
4. **Documentation/storage:** add an ownership guide, distinguish current commands
   from historical reports, link this migration from older handoffs, and ignore all
   local `_build*` trees. Keep retained evidence separate from authored harnesses.
5. **Verification and handoff:** run meaningful standalone hardware, declaration,
   bundle/CLI, and provider/source-inventory checks; document environment failures
   precisely and record cross-repository follow-up for later Workbench sessions.

## Workbench configuration direction and boundary

The desired entry point is `.workbench/project.sexp`, with independently optional
sections for source build/elaboration/bundle generation, ASIC execution, and
simulation. Multiple included files are acceptable if needed. Hardware clocks,
ports, resource requirements and flow catalogs remain in the OCaml declaration.

"Preparation" currently means building the checkout and generating its bundle,
not installing tools. Future user-facing configuration should name that function
explicitly (`source_build`/`bundle_generation`), while preserving protocol semantics.

Current Workbench readers require three root companion filenames. Moving those
files alone would break discovery. This migration updates example-side active
paths while retaining the supported companion contract. The unified loader,
relative-path policy, local overrides, setup ownership rules and compatible
discovery require a coordinated follow-up in `hardcaml_workbench`, which is outside
the repositories authorized for edits in this session. Do not publish an inert
`.workbench/project.sexp` pretending it is already supported.

Do not move existing installed generations, toolchains, live daemon state or
results. `.dev/` currently also contains historical experiments/results; their
presence is legacy storage, not the intended definition of development state.
New setup must identify its source layout and give an actionable diagnostic for
legacy editable projects rather than assuming additive source import handles moves.

## Prior migration records and handoff currency

* `../workbench_development_handoff.md`: development-store/source-copy contract,
  explicit imports, owned support updates, and historical acceptance. Its final
  recorded selected generation is `26f0d5e474bc4d45b5fc5859325c162d`; read-only
  inspection on 2026-11-10 found selection `a3553c69bfb940a4bedadeb345415b01`.
  Thus its historical result is useful, but it is not current selection authority.
* `../workbench_git_context_handoff.md`: scoped Git provenance for copied sources.
* `../pt8_standard_plan_recovery.md`: complete source closure/private setup recovery.
* `../pt7_timing.md`: historical public timing API migration, not a layout plan.

The selected store manifest is runtime-selection authority. Do not infer a running
daemon or its version from a historical document or a selected manifest alone.

## Implementation policies

* No Git add/commit/push, author/config changes, or AI-attributed GitHub actions.
  Existing isolated fixture scripts may use their documented Git operations.
* Aggregate build/job allocation is at most **20**. Allocate at most **6** to each
  of three implementation agents (18 total); management checks are serialized or
  use the remaining 2. Set native thread limits where relevant. No physical EDA or
  provisioning is needed for source organization.
* Use up to three general implementation agents with disjoint file ownership.
  The main session owns this plan, user communication, documentation and review.
* Edits are authorized in `hardcaml_asic_example` and `hardcaml_asic`. Preserve
  unrelated working edits, especially the existing `acceptance/dune` change and
  untracked retained acceptance trees. Do not edit captured `.dev/` projects.

## Acceptance criteria

* Hardware/IP and ASIC ownership are visible in the tree; FIFO verification is
  IP-local and the timing family is visibly a tooling qualification fixture.
* Current executables, source manifests, imports, and copy closures use new paths.
* Ordinary verification remains PDK/EDA-free and bounded; a supported installed
  provider is selected explicitly for ASIC-dependent checks.
* Authored harnesses are not accidentally copied with retained evidence or built
  out of `_build*`, `.dev`, or archived snapshots.
* Existing local state and historical evidence are unchanged. Fresh-session paths
  and legacy-session limitations are documented for the next Workbench session.
* Final report names actual checks, failures/blockers, and remaining coordinated
  Workbench changes. No success is inferred from intended changes alone.

## Execution log

* Plan published before implementation. Baseline includes an existing modified
  `acceptance/dune`, untracked acceptance evidence, and unignored build trees.
* Three general implementation agents performed the hardware ownership, tooling
  qualification, and Workbench integration workstreams. Each was allocated at most
  6 jobs (18 aggregate); fresh Workbench builds used 2. No physical EDA,
  provisioning, installed dependency refresh, or Workbench rebuild was performed.
* Relocations follow the [exact path map](../repository_layout.md). Library names,
  FIFO hardware/model, wrapper logic, and hardware interfaces are preserved. The
  combined program-memory module remains combined. IP-specific verification did
  not move into a root shared-verification bucket.
* Active source inventories, synthetic source fixtures, relative imports, Dune
  relationships, installer defaults, CLI consumers, and fresh-session source
  captures were updated. Python protocol utilities have one explicit integration
  owner. Independent/relocated captured imports were checked without owner access.
* Existing `.dev/` projects and generations remain in their old layouts. The new
  setup records `ownership-v1` and rejects legacy stores with an actionable new
  `--store` diagnostic before modifying them. Arbitrary existing user edits are not
  merged or overwritten by an implicit migration.
* The prior README was preserved under `docs/archive/`; the new root README is the
  current build/layout entry point. Historical handoffs link forward to
  [Workbench continuation](workbench_continuation.md).
* An integrated `@all` build exposed Dune traversing retained SRAM/resource source
  snapshots. `acceptance/dune` now marks **all child directories data-only**, which
  includes the user's original three exclusions without editing captured files.
  The subsequent integrated build passed.

### Actual verification

All ASIC-dependent checks selected the already installed provider
`ee3af8de9f83418b9afed9c67e473e3c` under
`.dev/asic-pt8-workbench/session-final-review-01/asic/generations/`. Native-thread
limits were 1. The native simulation adapter used `.dev/workbench-provider-sdk`.

* **Full active build:** `dune build --build-dir _build_migration_review -j6 @all`
  passed after evidence isolation.
* **Root regression:** `dune runtest --build-dir _build_migration_review -j6`
  passed: FIFO core and wrapper directed/seeded checks, resolution/catalog, memory
  behavior/policy, timing fixture, bundle deterministic/provenance/RTL replay and
  corrupted-oracle checks, CLI, 24 dependency tests, 11 bootstrap tests, and 21
  routing cases (one optional installed-native fixture case explicitly skipped).
* **Independent hardware source copy:** nine relocated targets built from the
  complete 204-file authored capture outside the checkout, with no `acceptance/`
  tree and no missing local source dependencies.
* **Tooling qualification:** twelve executable targets built; five positive
  variant simulations passed and the ignored-depth negative failed as intended;
  unsupported Exact128 rejected. Thirteen route/variant/workload bundle emissions
  had verified source bytes/hashes. A later fresh-copy audit checked six bundle
  families including program memory. Seventy-two Python entry imports passed;
  two native API probes were syntax-checked only.
* **FIFO bundle:** actual-checkout deterministic emission, declared source hashes,
  and both synthesis/simulation RTL replay passed 11,429 edges each, with deliberate
  corrupted traces rejected. Flop-memory operation/RTL matrix passed separately.
* **Physical-record utilities:** ten pure Python tests passed. No physical run was
  launched, and no new timing/physical acceptance claim is made.
* **Fresh Workbench lifecycle:** 15/15 native integration checks passed in a new
  private `/tmp/opencode` store after retaining/fixing an initial scoped-test failure.
  Includes normal/mismatch simulation, both PT8 workloads, cancellation, waveform
  validation, source build/plan/emission, publication/recovery, and scoped Git.
* **Resource-preparation integration:** 89 native checks passed. The synthetic
  source fixture now has independent Git metadata rather than accidentally
  discovering the enclosing checkout. Provider receipts follow the selected
  installed provider, not an unrelated hard-coded development store.
* **Layout/install checks:** five copy/import/layout regressions and twelve
  simulation-installer fixture tests passed. Active syntax/import checks passed;
  `git diff --check` passed. The five layout regressions also passed through the
  declared Dune alias `@scripts/ownership-layout-test` in `_build_migration_review`.
* **Preservation:** the integration audit observed unchanged repository index,
  pinned root ASIC/simulation configs and executable hashes, and no metadata
  changes across 124,663 preexisting `.dev/` entries. Agent hardware review
  accounted for all 49 moved authored files in its workstream, with no lost files
  or executable-mode changes. Historical acceptance trees were not rewritten.

The root build/regression commands used `opam exec --switch=5.2.0+ox --` with an
explicit `OCAMLPATH` containing the provider's `lib` and the SDK's `lib`; they do not
imply those APIs are available in the default global installation.

### Remaining coordinated work

* Implement `.workbench/project.sexp` discovery/schema, relative paths and local
  override semantics in Workbench, updating installers/capture ownership together.
* Deliberately choose a new migrated development store and reconcile any wanted
  edits from an old editable project; this migration did not switch the user's
  active project or installed applications.
* Recursive bundle-fixture execution within the copied project's scoped-Git
  environment remains a separate fixture-context issue. The fresh lifecycle suite
  uses exact aliases to preserve its original ordinary-test scope; root-checkout
  recursive regression and bundle replay passed independently.
* Continue with [the explicit Workbench handoff](workbench_continuation.md). No
  changes were required in `hardcaml_asic`; `hardcaml_workbench` was read only.
