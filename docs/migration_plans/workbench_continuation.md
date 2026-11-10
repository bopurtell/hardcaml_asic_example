# Workbench continuation after the ownership-layout migration

Date: 2026-11-10

This is the current continuation entry point for the reorganized example.
Read [the layout guide](../repository_layout.md) and
[migration execution record](ownership_layout.md) first.

## Subsequent developer-workflow closeout

Workbench now records [independently reviewed synthesis/collection and restart
acceptance](../../../hardcaml_workbench/docs/developer_workflow_refactored_closeout.md)
on a new ownership-v1 private store. The later installed provider generation is
`36205ea4748c4972877ac198356d8e44` under `.dev/asic-synthesis-envelope-v1/generations/`.
Its opt-in `prepare --synthesis-task-limit 6` captures a kernel-enforced six-total-
container-task synthesis envelope; normal refresh retains that setting. This is
synthesis-only, reduces usable concurrency, and does not imply physical signoff.
The active provider publicly advertises synthesis-only report collection; compatible
Workbench apps admit collect but continue to reject synthesis acceptance/signoff.

Explicit `prepare --refresh --apps-only` can capture reviewed replacement app bytes
while retaining companion configuration/history scope. It requires expected app
hashes and rejects source/dependency drift. It was fixture-tested, but the accepted
workflow used a fresh store instead. No existing owner's store or root companion
selection was migrated. The closeout records the exact captured app hashes and
temporary evidence paths; use those identities rather than assuming the historical
installed inputs below are the newly accepted pair.

## What changed

Active source now has IP-owned RTL/verification, ASIC-owned integration/system
verification, and separate tooling acceptance. Workbench helpers use explicit
imports and copy inventories for that layout (`source_layout: ownership-v1`).
`scripts/workbench_dev.py` and `scripts/workbench_git.py` remain entry points.

The preparation companion builds `asics/fifo_demo/cli/project.exe`. Root ASIC and
simulation companions still point to their prior installed executables. A source
move does not upgrade their binaries or change old result attribution.

The old `workbench_development_handoff.md` describes the previous source layout
and records older selected generations. Its session locking, provenance, and
immutable-capture rationale remain background, not current command/selection
authority. In particular its `prepare --refresh --import-missing-source` sequence
is an additive migration, not a directory-move migration.

## Existing sessions and new sessions

No existing `.dev/` editable project, selected generation, history, preferences,
daemon, or captured executable was migrated during source reorganization.
Do not point a historical project executable at relocated source and assume it
works: historical binaries contain their original declared source inventories.

The updated setup rejects a legacy development store before changing its locks,
publication, or project. It explains that an explicit **new `--store`** is needed.
Retain older stores and any edits they contain; reconcile wanted edits deliberately
against the path map instead of recopying over them.

For a fresh session, choose a new absolute store path and select existing compatible
dependency/SDK/app artifacts. The helper builds the example, not Workbench itself:

```sh
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_dev.py \
  --store /absolute/new/development-store prepare \
  --asic-generation /absolute/installed/asic/generation \
  --sdk-prefix /absolute/workbench-provider-sdk \
  --wb-build-root /absolute/workbench/build-root

opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_dev.py \
  --store /absolute/new/development-store status
```

The same store must be selected for later commands. When the owner elects to start
that session, `daemon` and `client` are explicit separate subcommands. Neither is
implicitly launched by preparation. Edit that store's `project/` for subsequent
development; it is an independent copy, not an auto-synced checkout view.

Fresh setup uses a private build and at most two Dune jobs. Total simultaneous
build allocation across sessions must remain at or below 20.

## Supported configuration versus intended configuration

Today the Workbench loader still discovers three regular root companions:

| Companion | Role |
| --- | --- |
| `hardcaml-workbench-preparation.sexp` | Build the current source project, elaborate, and emit its bundle. Does not provision tools. |
| `hardcaml-workbench-asic.sexp` | Select project/provider executables, toolchain, physical result storage, and time budget. This is Workbench integration config. |
| `hardcaml-workbench-simulation.sexp` | Select the simulation provider and discovery/run budgets. |

The requested future interface is `.workbench/project.sexp`, with optional
source-build/bundle-generation, ASIC-execution, and simulation sections.
Multiple included files are acceptable. Do not duplicate the hardware/flow
declaration from OCaml in that file.

### Follow-up in `hardcaml_workbench`

1. Define the unified versioned schema and discovery precedence, including explicit
   conflict behavior when unified and legacy companions coexist.
2. Define project-root-relative paths and machine-local overrides so checked-in
   configuration need not embed one workstation's absolute paths.
3. Route unified sections to the existing preparation/ASIC/simulation capabilities;
   preserve their independent opt-in behavior and explicit physical launch.
4. Update setup/install helpers, regular-file admission, ownership/hash tracking,
   publication/recovery, and captured-source inventories together.
5. Verify fresh projects, existing companion projects, copied projects, and retained
   sessions with real discovery/build/emission/simulation checks. Carry existing
   scoped-Git and independent-capture guarantees forward.
6. Update user-facing naming: preparation here means source build and bundle
   generation. Provider resource-preparation APIs are a separate concept.

No Workbench source was edited in this migration, and no unsupported unified file
was installed. Edits in this session were confined to `hardcaml_asic_example`.

## Verification available to the next session

Installed provider used:
`.dev/asic-pt8-workbench/session-final-review-01/asic/generations/ee3af8de9f83418b9afed9c67e473e3c`.
SDK: `.dev/workbench-provider-sdk`.

The fresh isolated lifecycle run passed **15/15 checks** and exercised source
compilation, native FIFO normal/mismatch checking, both PT8 workloads, VCD/checker
validation, cancellation/reaping, source drift, source planning/build/emission,
scoped Git, metadata-only native preflight, and private publication/recovery.
Its daemon was private to the check and was stopped by that check. Independent
captured and relocated helper imports made zero owner-checkout accesses.

Native resource-preparation verification passed **89 checks** against the selected
installed reader. This checks resource declaration/inventory evidence, not physical
EDA results. No synthesis/place-and-route or tool provisioning was performed.

Evidence from this session (temporary local storage, not a committed archive):

```text
/tmp/opencode/ownership-c-native-20261110-02/test-evidence/
  result.json
  standard-source-flow/
  independent-captured-imports/receipt.json
  native-preparation-02.command.json
  native-preparation-02-check/report.json
  preservation.json
```

The first isolated lifecycle attempt retained a failure caused by newly recursive
bundle-test inclusion. The corrected session uses exact aliases to retain the
original ordinary-test scope. This does not claim recursive bundle replay inside
the scoped-Git copied-project environment; root-checkout bundle verification is
checked separately. The earlier failed evidence remains in its separate store.

The preservation audit reported no metadata changes among 124,663 existing `.dev/`
entries and unchanged root pinned executable/config hashes and repository index.
These are observations of this migration, not promises about later sessions.
