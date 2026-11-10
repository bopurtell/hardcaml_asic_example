# Stable Workbench development session — B handoff

> **Historical layout / status (2026-11-10):** source directories and setup scopes
> below precede the ownership migration. The final selected-generation snapshot is
> also older than the currently observed selection. For current source paths and
> fresh-session instructions, read [Workbench continuation](migration_plans/workbench_continuation.md).
> Existing stores were preserved; the additive import commands below do not migrate
> moved directories. The current helper requires an explicit new store for that case.

**Git-context correction:** the running owner's earlier capture exports unsafe
global Git repository selectors. It has NOT been refreshed/stopped by B. See
[`workbench_git_context_handoff.md`](workbench_git_context_handoff.md) for the
scoped dispatcher, private acceptance capture and explicit owner-stopped recovery.

2026-11-05. Implementation contract published before acceptance. B owns the example
router, preparation/launcher, PT8 cancellation correction and example tests. C owns
independent Workbench integration verification. Acceptance results are appended below.

## CLI (from the example checkout, switch 5.2.0+ox)

```sh
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_dev.py prepare
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_dev.py daemon
# Separate terminal; never starts a daemon implicitly:
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_dev.py client
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_dev.py status
# Stop the development daemon explicitly before refreshing:
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_dev.py prepare --refresh
```

Global `--store ABS` selects an independent store for verification; put it BEFORE
the subcommand. `--root ABS` selects the initial source checkout (default is the
example checkout containing this script). Neither option changes the canonical
project after preparation. C should use `--store /tmp/opencode/<private-root>`.

`prepare` options: `--refresh`, `--asic-generation ABS`, `--sdk-prefix ABS`,
`--wb-build-root ABS`, `--dune ABS`, `--git ABS`, `--import-missing-source`,
`--update-owned-support`, `--expected-client-sha256 HEX`,
`--expected-daemon-sha256 HEX`. Initial defaults are the exact ASIC generation
`.dev/asic-pt8-workbench/session-final-review-01/asic/generations/ee3af8de9f83418b9afed9c67e473e3c`,
SDK `.dev/workbench-provider-sdk`, sibling Workbench `_build_pt8_workbench`, and the
activated switch's `dune`. Refresh reuses recorded dependencies unless explicitly
overridden; it captures current prebuilt Workbench mains at the recorded build root.
The SDK defaults to the previous immutable generation's `sdk/` on refresh;
`--sdk-prefix` is required to explicitly select a different SDK installation.
No dependency provisioning/global opam install occurs. Client accepts extra client
options after `--`, but cannot override connection, project or environment.

## Fixed layout and transaction

```text
.dev/workbench-development/
  project/                  editable source-complete project; copied ONCE
  state/                    daemon-owned durable history/artifact/registry storage
  discovery/                daemon endpoint and lifetime lock
  client-state/             XDG_STATE_HOME for saved client state
  generations/<id>/         immutable source/scripts/apps/SDK/models/config capture
  builds/<id>/              private Dune output, never used as a runtime provider
  receipts/<id>/            preparation command output and failure/success receipts
  selected -> generations/<id>
  manifest.json -> selected/manifest.json
  prepare.lock
  publication.json          only present while publication/recovery is pending
```

The three `project/hardcaml-workbench-{simulation,asic,preparation}.sexp` files are
**regular files**, not symlinks. The production FS2 reader deliberately rejects
symlink components; its admission policy is unchanged. Preparation holds the setup
lock and BOTH daemon state/discovery lifetime locks across config publication and
selection. An active daemon causes explicit refresh to fail.
Daemon startup is serialized against preparation. No command stops/restarts another
process. Failed preparation keeps the prior selection, source and all state intact.
The foreground daemon inherits a shared `prepare.lock` fence across exec; clients
and idempotent verification also take shared ownership. Captures require exclusive
ownership plus both state/discovery lifetime locks. App-pair capture takes the shared
Workbench build lock, verifies source/copy hashes before and after, and never builds
Workbench itself. Generation files are fsynced and made read-only before publication.

Config publication first saves/fsyncs rollback bytes and an intent journal, then
atomically links that complete journal as `publication.json`. It replaces each
regular config atomically, changes `selected` last, verifies the exact selected
config hashes, and commits by moving the journal into the receipt. An ordinary
failure rolls back configs/selection under the same locks. A crash leaves the
journal: launch/status/repeat prepare refuse with an explicit `prepare --refresh`
recovery instruction. That explicit refresh validates every config is still one of
the journal's known old/new states and verifies backup hashes before rollback and
retry. Unknown edits block recovery and are never overwritten; reconcile those
files with `publication.json` and its receipt before retrying. A pending journal
is not an instruction to manually delete it or change selection.

Older symlink captures (including `c9b4564df7914fd4ac8b5d20dcd0cf34`) migrate ONLY
through explicit `prepare --refresh`. Setup checks their exact owned link targets,
captured config hashes and immutable generation inventory before replacement.
Modified links/target bytes are refused. Old generations remain unchanged.

Repeat `prepare` verifies the installed capture without rebuilding/overwriting.
Source drift is reported separately, not repaired. Refresh captures/builds FROM
`project/`, preserving edits. Owner-checkout source updates are never auto-synced.

### Bounded authored source closure and explicit additions

Initial copy and immutable generation inventories now contain:

```text
lib/ asic/ bin/ memory/ variants/ workloads/ simulation/ test_support/ scripts/
test/ asic_test/ timing/ named_timing/ physical_timing/
dune-project asic-dependency.json README.md bootstrap.sh
acceptance/{dune,export_trace.ml,check_bundle.py,replay.v}
```

Only those four authored acceptance harness files are included. Retained acceptance
snapshots/results, `_build*`, `_flow_tools`, `_flow_results`, `.dev`/Git stores,
Python caches and other generated stores are excluded. Executable source-file modes
(including bootstrap.sh) survive the independent copy. The bounded ordinary test
gate is `dune runtest --root PROJECT -j2 test asic_test timing`; optional physical,
provisioning and historical acceptance workflows are not invoked by preparation.

Existing development roots acquire missing authored entries ONLY through:

```sh
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_dev.py prepare \
  --refresh --import-missing-source --update-owned-support
```

Both migration flags require explicit `--refresh`. Imports use the recorded
`source_owner_root` (old manifests derive it from their recorded Git-context root),
not a newly supplied arbitrary `--root`. Approved additions are the five newly
included directories, bootstrap.sh and the four-file acceptance harness as a single
directory. Each directory must be entirely absent; existing directories, including
empty directories and symlinks, are NEVER merged or replaced. Source/staged-copy
hashes are rechecked, staged bytes/directories are fsynced, and Linux atomic
`RENAME_NOREPLACE` installs them without overwriting a racing user's new path.

`--update-owned-support` separately and explicitly updates only B's router, launcher,
acceptance test and focused waveform test files. Existing bytes must equal the
previous generation's recorded source baseline; unknown edits and symlinked files/
parents refuse. The old bytes are moved to a no-replace receipt backup, rechecked,
then new bytes are installed only into an absent path. A racing editor's replacement
is not overwritten, and displaced original bytes remain in the receipt. No other
source file is updated. This makes the private router's SOURCE_DIRS/SOURCE_FILES
metadata match the actual new closure without replacing arbitrary project edits.

Durable `source-migration-intent.json` and `source-migration-result.json` receipts
record the owner root, per-file hashes, baseline hashes and installed entries;
support backups and uninstalled stage copies remain inspectable. Added sources
are deliberately retained if a later source build/refresh fails; selection/configs
still retain their previous generation. An interrupted source import can be
reconciled from its receipt and explicitly retried; no automatic deletion or source
rollback erases additions or editor changes. Repeat prepare never imports sources.

`--expected-*-sha256` fences the prebuilt app capture under the Workbench build lock;
a mismatch fails before building/switching. These expectations apply to this explicit
capture, not an automatic app-upgrade policy.

## Manifest schema 1

The immutable `generations/<id>/manifest.json` has:

* `schema_version`, `generation_id`, `generation`, `store`, `project_root`;
* `paths`: fixed `state`, `discovery`, `client_state`, `project` paths;
* `inputs`: absolute `asic_generation`, `sdk_prefix`, `wb_build_root`, `dune`,
  `python`, `toolchain`, `git_dir` paths (reused as refresh defaults);
* `environment`: exact `OCAMLPATH`, `HARDCAML_ASIC_GENERATION`, recorded base `PATH`,
  and the captured Dune shim's real-Dune/project-root variables;
* `source_files`: SHA256 inventory of the captured complete source closure;
* `source_owner_root`, `source_dirs`, `source_roots`: recorded initial owner and exact
  bounded authored closure; status reports any `missing_source` entries;
* `source_migration`: optional receipt path/SHA256 and installed source-entry list;
* `suite_sources`: per-suite relevant-source inventories checked before run;
* `provider_commands`: `controlled-fifo` and `pt8-memory-workloads` argv prefixes;
* `provider_command`: composite argv prefix;
* `apps`: captured `daemon` and `client` paths and SHA256;
* `config_files`: exact filename→SHA256 map for all three installed regular configs;
* `setup`: actual installer source path, captured setup path and SHA256 (distinct
  from a possibly older launcher source file in the preserved editable project);
* `git_context`: pinned real Git path/SHA256 and exact source-root metadata map;
  source Git metadata is not exported in the base environment. Status supplies
  `git_context_diagnostic` for older unsafe captures without rewriting history;
* `captured_files`: generation-relative file SHA256 inventory (excluding manifest);
* `asic_receipt_sha256`, `asic_files`: exact external immutable ASIC capture inventory;
* `max_jobs: 2`, `eda_allocation: 0`.

Commands are absolute paths, not shell strings. Runtime uses captured files, not
the SDK input prefix or mutable Workbench build outputs. ASIC generation is reused
by its exact immutable path, never `current`. The source snapshot identifies actual
bytes, not an enclosing Git revision. VCD/report artifacts remain daemon-owned;
PT8 full results persist below `project/.dev/asic-pt8-workbench/workloads/`.

The existing immutable ASIC reader requires HEAD/porcelain source context. New
captures use the pinned real-Git dispatcher described in the Git-context handoff:
only Git processes directed at the exact private project/source-snapshot root get
the owner comparison context. There are NO globally exported repository selectors;
collateral probes discover their own repositories. Inherited selectors/config
injection are sanitized. Read-only optional-lock/config controls remain. The earlier
global GIT_DIR/GIT_WORK_TREE design was a real collateral-validation bug and is
superseded; historical captures/results are preserved, not silently repaired.

## Composite FS2 contract

`simulation/workbench_provider.py --manifest ABS discover --protocol-version 1`
returns the exact FIFO-then-PT8 child catalog union. Invalid, failed, duplicate or
oversized discovery never yields a partial catalog. Discovery launches no builds
or simulation. Run only reads a bounded request to choose its suite and check its
source capture, then execs the selected child with the original FS2 arguments.

* FIFO: captured `test_provider.exe --simulator ABS/fifo_sim.exe`.
  Suite `controlled-fifo`; directed/seeded; checker normal/mismatch; cycles
  64/4096/20000; canonical uint64 seed, default42.
* PT8: captured Python provider with exact `--generation`, `--producer-root`
  (fixed editable project), `--emitter`, `--model-root`.
  Suite `pt8-memory-workloads`; flops256/exact256; seed34097 only; no parameters.

No request/events/artifact path or attempt/case/artifact ID rewriting; no new
process group. Stale relevant sources reject before child execution/events with
`prepare --refresh`. ASIC Fresh may build current editable source independently.
The PT8 cancellation correction retains partial evidence and exits130 without
invalid provider `Incomplete` terminal events. FS2 owns cancelled/incomplete state.

## Review entry points

Load the selected manifest to obtain the router/provider commands. Invoke children
or router with standard FS2 discovery/run argv. Direct provider tests can use their
own request/events/artifact directories; native HTTP/UI tests must use an independent
`--store`, state, discovery and preferences. Do not mutate the user's stable store.
Builds use explicit root/private output, `-j2`, and shared example/ASIC/WB locks.

The manifest's `source_files` maps directly to `generation/source/<relative-path>`
for code inspection; `project/<relative-path>` is the editable working version.
Do not substitute an owner-checkout file for either one. Relevant source additions,
edits, deletions or symlink replacements invalidate frozen simulation programs.
The guard is a pre-execution digest check, not an atomic lock against simultaneous
editor writes; avoid editing during a simulation. ASIC emission independently records
the actual declared input bytes in its retained bundle. Refresh preserves prior
generations rather than rebinding old evidence to new sources.

## Initial acceptance

**B initial milestone PASS**, ready for C's independent integration review.

```sh
opam exec --switch=5.2.0+ox -- python3 -B scripts/test_workbench_dev.py
opam exec --switch=5.2.0+ox -- python3 -B scripts/test_pt8_waveforms.py
```

Current source-closure/direct/lifecycle receipt (12 tests pass, including ordinary
project tests, migration/race tests and native FS2 Discover):
`/tmp/opencode/workbench-dev-b-jzc4uvlt/store/test-evidence/result.json`.
The earlier regular-config correction receipt (10 tests) remains
`/tmp/opencode/workbench-dev-b-t8l6wa8a/store/test-evidence/result.json`.
Original direct-only receipt remains
`/tmp/opencode/workbench-dev-b-2oy4yqrm/store/test-evidence/result.json`.
Focused producer regression: all6 tests pass after updating its cancelled-mode
assertion to require only the accepted `Started, Case_started` prefix.

The direct/lifecycle suite proves:

1. Exact native FIFO + PT8 catalog union; bounded stdout/stderr/timeouts, invalid
   discovery and no partial output; duplicate suites reject.
2. Real FIFO normal directed+seeded, seed0 and uint64 maximum; mismatch is semantic
   Failed/exit0 with full failure report and real VCD. Directed performs87955
   checks over7330 edges. Router/native events and reports agree byte-exactly
   (only VCD date metadata is normalized for comparison).
3. Real Flops256 and Exact256 implementation RTL simulation,1307 cycles each,
   retained result reinspection/expected digest, seven public metrics and published
   VCD bytes equal the actual simulator output. Both complete Passed.
4. Bad suite/case/options/seeds reject without events or artifacts; exec routing
   preserves provider PID, inherited process group and every forwarded FS2 argument.
5. Real FIFO group cancellation and PT8 PID-only cancellation observe/reap their
   owned native children and preserve a valid event prefix, with no forbidden
   provider Incomplete terminal events. PT8 retains partial producer evidence.
6. Idempotent prepare; source-edit/missing-source rejection; independent state and
   discovery lifetime locks reject refresh; failed build keeps the exact prior
   manifest. Successful refresh preserves source edits, old generations, retained
   PT8 closures/digests, state/artifact sentinels and preference sentinels.
7. Actual normal standard/balanced/synthesis Plan, source build through the captured
   two-job shim in `project/_build`, and emission from that rebuilt driver. The
   bundle contains the deliberately edited project source, distinct from owner
   source; captured/rebuilt plan identities agree. No physical run is submitted.
8. Actual foreground daemon/client launch in the private store, client API Get,
   idempotent prepare while daemon active, refresh refusal, explicit shutdown of
   only that test-owned daemon and client refusal to auto-start after shutdown.
   The corrected launcher gate also opens the project via real HTTP and submits
   production `/api/v1/simulation` Discover/Get; both original suites are advertised
   without discovery_error, using the regular installed config files.
9. Root configs, selected root provider/driver bytes and pre-existing modified
   `asic/project.ml`/`acceptance/dune` match their before/after hashes. Test receipts
   include every preparation command/failure and max_jobs2/EDA allocation0.

The state/history checks here use sentinels and real retained provider evidence.
C owns actual FS2 HTTP history/artifact identity/restart/rerun and production UI
Testing/Workloads/Waveforms verification; this document does not claim those gates.

Retained failed runs:

* `workbench-dev-b-ftyl06vp`: first private `/tmp` PT8 emitter lacked enclosing Git
  context; no simulation ran for that pair. Read-only explicit context corrected it.
* `workbench-dev-b-9wzvfxbj`: direct/source-flow gates passed, launcher test supplied
  a nonexistent terminal simulation CLI option. Corrected to supported ASIC Get.
* `workbench-dev-b-4k32ixg1`: all10 direct/lifecycle gates pass; subsequent existing
  waveform regression exposed its old expected cancellation terminal event.
  The focused assertion was corrected; prior receipts remain unchanged.

### Prepared user store

Fixed project: `/home/wayne/devel/jane/hardcaml_asic_example/.dev/workbench-development/project`.
Selected final source-closure capture: `generations/26f0d5e474bc4d45b5fc5859325c162d`.
ASIC generation remains exact `ee3af8de9f83418b9afed9c67e473e3c` above.
Captured app hashes:

* daemon: `ec0108fd3ae65ac8bc8113462bfc1eb4dcdcbecf6410c144fbc982113f495a38`
* client: `896cee9b6546be5c5d7fcd132306a55cf33cbc43d1c25edbd7cea9c467bd7a42`

Initial preparation and explicit refreshes were performed during implementation.
Only B's known new launcher/router/test corrections were explicitly applied to
their initially copied editable files before that refresh; other sources were not
recopied. All prior generations remain. No stable user daemon has been launched. All
acceptance daemon/client processes belonged to independent private test stores.

## C nofollow finding — corrected publication handoff

2026-11-05. C's `reviewdocs/tests/development-session-review.md` and native fail
receipts remain unchanged. The initial symlink configuration was a real integration
bug, missed by B's initial direct-provider and ASIC-Get tests. No daemon admission
code was changed. The corrected regular-file contract and recovery protocol above
supersede the original symlink publication design.

**B correction ready for C retest:** all10 tests pass, including actual production
native simulation Discover. Evidence:

* `/tmp/opencode/workbench-dev-b-t8l6wa8a/store/test-evidence/result.json`
* `.../launcher/native-discover.json`: complete production HTTP requests/responses,
  `passed=true`, `regular_configs=true`, exact controlled-fifo/PT8 suite IDs.
* `.../refresh.json`: regular config hashes, ordinary partial-publication rollback,
  simulated crash fencing/explicit recovery, changed configs not overwritten.
* `.../preservation.json`: unchanged owner configs/selected programs/source hashes.

Crash tests interrupt after the first config replacement, then verify launch/state
selection reads are fenced. An edit during interruption prevents recovery without
overwriting that edit. Restoring the known interrupted bytes and explicitly invoking
`prepare --refresh` rolls back all configs/selection before the deliberate failed
build; the exact old manifest remains selected. Ordinary injected publication failure
rolls back immediately. Existing source/history/artifact/preference retention tests
and native cancellation tests continue to pass.

The stable user's explicit migration receipt is:
`.dev/workbench-development/receipts/cbcd7f24ccf44b7e898f2a21145d1758/committed-publication.json`.
It records all three prior owned symlink targets/digests and the new regular hashes:

| File | SHA256 |
| --- | --- |
| `hardcaml-workbench-simulation.sexp` | `ac7c5bf256c7b8e22cc3e9868ee09b5fe84ac3193caecf38d02faced5ae2c44a` |
| `hardcaml-workbench-asic.sexp` | `3e3dc2f6b2292703c6100517aefe20eddc744b00c0d50972fd80689a9db90429` |
| `hardcaml-workbench-preparation.sexp` | `ad36f6c66e1966260aac2616cb8f260005b4175c47fb4c3085c6c71f7c2acf7b` |

No editable source was changed or recopied during this correction/migration. Setup
captures its actual new installer separately as `setup/workbench_dev.py`; source
snapshots still honestly contain the preserved editable scripts. Fixed project,
state/discovery/client-state, exact ASIC provider, prior app/provider generations and
retained results remain. C should explicitly refresh its independent store using
the owner checkout's corrected `scripts/workbench_dev.py`, then rerun its retained
native harness. This B check is not relabelled as C's independent acceptance.

## A source-closure finding — corrected and ready for independent recheck

2026-11-05. A's original37/38 review and receipts in
Workbench `docs/development_session_backend_review.md` remain unchanged. B corrected
the omitted authored source closure above and added explicit, non-overwriting
migration plus baseline-checked support updates. No A/C review script was edited or
its earlier result relabelled as a pass.

Latest B receipt: `/tmp/opencode/workbench-dev-b-jzc4uvlt/store/test-evidence/result.json`.
**All12 tests pass.** In addition to the original10 provider/lifecycle gates:

* Every approved source directory/file exists in both the initial editable copy and
  immutable source inventory; runtime router source and metadata use the new closure.
* Actual ordinary private `dune runtest --root PROJECT -j2 test asic_test timing`
  passes through the captured locked shim. Logs are in
  `.../standard-source-flow/ordinary-tests.{command.json,stdout,stderr}`.
  FIFO directed covers7330 edges; seeded covers20017 edges (20000 random cycles).
  Wrapper directed/seeded, catalog, resolution and timing-core reset/latency checks
  all pass. These are actual authored test targets, not test stubs or EDA launches.
* Legacy-project omission fixture: repeat prepare does not recopy; plain refresh
  refuses the missing closure; explicit import followed by a deliberately failed
  build retains all added bytes and the old selected generation. Subsequent import
  preserves a user edit to the existing FIFO test, and a real refresh captures it.
  Existing source/history/preferences and exact retained PT8 references survive.
* Source import publishes only the four authored acceptance files. A directory or
  symlink racing into a missing destination is not overwritten, including an empty
  directory; staged source bytes and receipts remain. Known-owned support updates
  retain checksum-verified baseline backups. Arbitrary edits and symlinked support
  parents are refused without overwriting their bytes. An explicitly wrong app hash
  refuses capture and leaves selection unchanged.

The exact user-authorized stable consolidation commands were:

```sh
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_dev.py prepare \
  --refresh --import-missing-source --update-owned-support \
  --expected-client-sha256 896cee9b6546be5c5d7fcd132306a55cf33cbc43d1c25edbd7cea9c467bd7a42 \
  --expected-daemon-sha256 ec0108fd3ae65ac8bc8113462bfc1eb4dcdcbecf6410c144fbc982113f495a38
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_dev.py prepare
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_dev.py status
```

The first explicit consolidation capture was `8165bd3ad86c45a8af2278a16d429b60`;
its `receipts/<id>/source-migration-result.json` inventories the five imported
directories, bootstrap/acceptance harness and exact baseline-checked support changes.
After the additional support-parent guard, another explicit refresh selected
**`26f0d5e474bc4d45b5fc5859325c162d`**, with the exact requested app hashes above.
The latter receipt records only the baseline-matching launcher/test update; existing
directories were not recopied. Both captures and all earlier generations remain.

Final real `status` excerpt (repeat prepare selected the same generation):

```json
{
  "prepared": true,
  "editable_project": "/home/wayne/devel/jane/hardcaml_asic_example/.dev/workbench-development/project",
  "generation": "/home/wayne/devel/jane/hardcaml_asic_example/.dev/workbench-development/generations/26f0d5e474bc4d45b5fc5859325c162d",
  "source_drift": {"controlled-fifo": [], "pt8-memory-workloads": []},
  "missing_source": []
}
```

The stable daemon is still not started. Fixed source/state/discovery/client-state
paths remain. No root config, existing provider generation, live pair or Git state
was changed, and no global install or EDA occurred. All Dune used explicit roots,
private output, at most2 jobs and shared locks. C/A may now recheck this closure in
independent private stores; existing incomplete stores need both explicit migration
flags, while new prepares receive the corrected closure immediately.
