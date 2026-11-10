# PT8 private standard-flow recovery

> **Historical recovery record:** commands/source paths below describe the original
> sessions. For the current layout and new-session boundary, see
> [Workbench continuation](migration_plans/workbench_continuation.md).

## Bounded plan (written before correction)

2026-11-05. Owner: example/setup recovery slice. The existing
`session-final-review-01` remains immutable and its running daemon is untouched.
Workbench/backend changes require coordinator agreement; frontend is another slice.

1. Recover the failed standard Plan job/argv and logs through read-only inspection;
   reproduce with its captured FIFO binary against the config-only project, saving
   command, status and stderr in a new recovery evidence directory. No EDA.
2. Correct new-session setup to capture a complete independent example source
   snapshot (excluding generated/retained/tool/provider trees and root configs),
   with private ASIC, simulation and preparation configs. The stock captured
   driver can then use the real private source root without path rewriting.
3. Activate the selected captured provider in setup and launcher for nested builds.
   Use switch `5.2.0+ox`, explicit `-j2`, and shared ASIC/example locks; any WB
   build uses `/tmp/opencode/workbench-pt8-build.lock`. Preparation must build and
   execute in the private project, with all writable build/results/state paths
   inside the new session. Tool/PDK collateral may be read from the owner tree.
4. Create a new immutable recovery session, retaining all old sessions/failures.
   Verify standard public Plan for every advertised endpoint, emit a real bundle,
   and use private native HTTP to stage a Fresh request and verify launch
   availability. Exercise actual source build/emission through standalone
   preparation; do not submit a physical launch. Check PT8 discovery remains usable.
5. Retain exact commands/hashes/failures and preservation checks. Main owns the
   integrated UI review and decision to use the new launch pair.

Preservation scope: all existing root configs and their selected programs, existing
session config/provider files, original retained evidence, and pre-existing source
mods/untracked files. No normal root config, source, immutable provider or generated
root output is an edit destination; only authorized example scripts/docs and new
isolated session/build directories are changed.

## Investigation and correction

**PASS for the bounded source-only/native HTTP acceptance.** Coordinator integrated
review remains separate. New session: `.dev/asic-pt8-workbench/session-standard-recovery-02`.
The existing `session-final-review-01` daemon/client remain running, with their
configuration and immutable installed/provider files unchanged.

Failure evidence is retained in
`.dev/asic-pt8-workbench/recovery-investigation-ab7537b3043b45b99c6f6d967a30593b/`.
Read-only native Get/snapshot found no historical Plan job/log in the current live
daemon. Therefore the original click's endpoint/argv cannot be recovered from that
daemon; `repro.json` is explicitly a newly executed reproduction of the adapter's
standard/balanced/synthesis invocation, not a recovered historical receipt:

```sh
S="$PWD/.dev/asic-pt8-workbench/session-final-review-01"
"$S/provider/project.exe" flow plan --flow standard --profile balanced \
  --endpoint synthesis --source-root "$S/project" --json
```

Cwd was `$S/project`. Exit **1**, empty stdout, stderr reports eighteen missing
declared source inputs (README, dependency record, ASIC/catalog/bin/lib sources).
Binary SHA256: `4601f9435dc4f964dc3ad18f0aea40705fff06107dd550f923dad8e98c6bd0ba`.
The same **old captured binary**, pointed at the new independent source closure,
successfully plans without a rebuild or EDA. That isolates the missing source root
as the cause rather than a provider or RTL defect.

Corrections are confined to example scripts:

- `pt8_workbench_setup.py`: copies the FIFO + PT8 build/source closure with real
  independent files, inventories/rechecks source hashes, builds inside the new
  project with explicit `--root`, and writes private preparation/ASIC/simulation
  configs. PT8 producer root is now the private project too, so its future retained
  output goes under that project's `.dev`, never the owner's root store. Existing
  configs are not copied/adopted. New setup names must not already exist.
- `--reuse-provider-session` validates the previous captured provider files and
  explicitly reuses its immutable ASIC generation without refreshing or rewriting
  it. This recovery uses generation `ee3af8de9f83418b9afed9c67e473e3c` and receipt
  SHA256 `12485d394046661f9571e4d6144bfe666fac45fb6f0ef11468b6445894f2732d`.
- `pt8_workbench_launch.py`: activates that exact generation's `OCAMLPATH`, PATH and
  generation variable for new source-complete sessions, including nested Dune
  builds. Optional `--runtime-root` puts independent acceptance discovery/state
  below the session. Existing session manifests retain their old launch behavior.
- `pt8_workbench_dune.py`: new captures enforce **two** jobs under the example lock;
  options precede `--`; build output is the private `_build/default` that stock
  preparation executes. Setup prebuild is a separate private `_build_pt8_workbench`.
  Existing sessions' captured shims are unchanged.

No Workbench/backend/frontend or ASIC source was edited or rebuilt by this slice.
The snapshot has no Git checkout of its own: provider manifest `source_revision`
is enclosing-checkout context, **not** a commit containing the private snapshot or
a clean-tree assertion. `source-snapshot.json` and per-input bundle hashes identify
the captured source bytes, including the existing modified `asic/project.ml`.

## Actual commands and evidence

From `/home/wayne/devel/jane/hardcaml_asic_example`:

```sh
opam exec --switch=5.2.0+ox -- python3 -B scripts/pt8_standard_recovery.py \
  --session .dev/asic-pt8-workbench/session-final-review-01
opam exec --switch=5.2.0+ox -- python3 -B scripts/pt8_workbench_setup.py \
  --session session-standard-recovery-02 \
  --reuse-provider-session .dev/asic-pt8-workbench/session-final-review-01
opam exec --switch=5.2.0+ox -- python3 -B scripts/pt8_standard_acceptance.py \
  --session .dev/asic-pt8-workbench/session-standard-recovery-02 \
  --protected-session .dev/asic-pt8-workbench/session-final-review-01
git diff --check
```

Passing evidence below the new session:
**`standard-acceptance-ed6ab6eccce14666a2ab861a63fddf02/assertions.json`**.
The setup's `commands/02/command.json` records the real private prebuild:

```sh
dune build -j 2 --root "$SESSION/project" --build-dir _build_pt8_workbench \
  workloads/workload_emit.exe workloads/workload_public.exe bin/project.exe
```

The real switch Dune exec in the native process trace (line10983) is:

```sh
/home/wayne/.opam/5.2.0+ox/bin/dune build --root "$SESSION/project" \
  -j2 --build-dir "$SESSION/project/_build" -- bin/project.exe
```

Both builds hold `/tmp/opencode/example-pt7-build.lock`. No ASIC/WB build was
needed; future fresh ASIC capture uses explicit `-j 2` under its shared ASIC lock.

Observed gates:

1. Native HTTP Discover advertises standard profiles `balanced` and `synth_delay`,
   and all seven endpoints: synthesis, floorplan, placement, CTS, routing, timing,
   signoff. All **14** real native HTTP Plan requests pass; actual argv/responses
   are retained in `http.json` and `process.strace`.
2. Real public `flow emit` publishes a bundle below the new acceptance directory.
   Balanced/synthesis plan identity is
   `744f43a3ffe46550b97b84055079e46446c0e588cf564b07a35322eb8cd3c87f`;
   bundle identity is
   `44402053ca60796f343c78928af0bc17673ad0b6972a78c65fa9ec27cff1b55c`.
3. Native physical `Stage_fresh` returns a valid intent with the private source and
   complete configuration scope. Preparation reports **Available**. No physical
   Launch request is submitted.
4. Unified `Stage_fresh(elaboration_only=true)` → `Launch_fresh` completes real
   source build then emission, with both jobs Complete and the same plan/bundle
   identities. Prepared bundle is in `session-standard-recovery-02/preparation-results`;
   exact methodology bytes/digest are captured in the acceptance's private state.
   Workflow has no run/reference. Final physical intent staging succeeds again.
5. PT8 native simulation discovery still advertises the workload suite. No new
   simulator or physical execution is made in this acceptance.
6. Root configs/selected programs, full old installed/provider/config inventory,
   new installed/provider/config inventory and private source hashes match before
   and after. The trace contains no provider `stages` admission or EDA process.
   Only the acceptance-owned daemon is stopped/reaped (exit -15).

Tested Workbench binaries (prebuilt by their owners): daemon SHA256
`ec0108fd3ae65ac8bc8113462bfc1eb4dcdcbecf6410c144fbc982113f495a38`;
terminal SHA256 `3ada8c5818733e7588fb732283e92a2402efb1677c92d436352f8be0a1e83e18`.
The new captured FIFO binary has the same SHA256 as the original above.

### Retained recovery failures

- `session-standard-recovery-01/commands/02`: initial Dune build omitted `--root`.
  Dune climbed out of `.dev` to the owner root, then exited1 with `Don't know how
  to build workloads/workload_emit.exe`; it did not compile targets. Its diagnostic
  build-cache/log activity was therefore at the owner's existing
  `_build_pt8_workbench`, an unintended early-attempt side effect. This is retained
  and disclosed, not claimed as a fully isolated successful attempt. Explicit
  `--root` fixes this; all successful builds use the private project.
- `standard-acceptance-76f8bf68db444d8d9bb422e54d404ff5`: daemon rejected duplicate
  discovery/state flags before startup. Fixed with explicit private runtime-root.
- `standard-acceptance-5281da30575a48fcb45b01c752edeb6d`: all Plans and actual
  build/emission completed, then harness log retrieval exceeded native bounds.
  Corrected to100 records/65536 bytes. This failed receipt is unchanged.
- The final acceptance above exits0. `git diff --check` exits0. Original tracked
  modifications remain only `acceptance/dune` and `asic/project.ml`; existing
  untracked/retained/provider files remain present. The new owned files are the
  recovery doc/scripts plus the three authorized setup/launch/shim corrections.

## Coordinator review launch pair

Run only when choosing to review the **new** session, in separate foreground terminals:

```sh
opam exec --switch=5.2.0+ox -- python3 -B scripts/pt8_workbench_launch.py daemon \
  --session .dev/asic-pt8-workbench/session-standard-recovery-02
opam exec --switch=5.2.0+ox -- python3 -B scripts/pt8_workbench_launch.py client \
  --session .dev/asic-pt8-workbench/session-standard-recovery-02
```

No replacement of the running `session-final-review-01` pair has been attempted.
Integrated UI staging/launch-control review belongs to main; actual physical
execution is intentionally outside this zero-EDA acceptance.

## C final private-snapshot PT8 provider verification

**PASS**, 2026-11-05: one real direct-FS2 `exact256` implementation simulation,
fixed seed34097. This closes the earlier discovery-only limit after changing the
producer source root to the private snapshot. No provider/source/config setup was
changed. Existing `pt8_workbench_acceptance.py` hardcodes the owner workload-store
path in its assertions, so this focused follow-up uses a separate additive harness
rather than rewriting that historical full-suite harness or running extra cases.

Actual command, from the example root:

```sh
opam exec --switch=5.2.0+ox -- python3 -B scripts/pt8_recovery_provider_check.py \
  --session .dev/asic-pt8-workbench/session-standard-recovery-02 \
  --protected-session .dev/asic-pt8-workbench/session-final-review-01
```

Evidence below the new session:
**`exact-fs2-verification-71641bf9eb1545e2b3c662519f26999f/assertions.json`**.
Provider discovery is real; the request selects only `exact256`. Captured emitter
argv uses `session-standard-recovery-02/project` as source, and all bundle,
simulation and result writes go below that project's private `.dev` directory.
Events have contiguous sequences and finish `Case_finished Passed`, `Finished Passed`.

- FS2 attempt: `recovery-exact-f12a31945cc447c0a4196ff4d3c6bcad`.
- Simulation attempt: `exact-bcb6c385f7fe4f9fad7b06938a46bd6c`.
- Retained result, relative to the new session:
  `project/.dev/asic-pt8-workbench/workloads/exact256-e5cec80fd231421c8257d7732efc7f4d/exact/result.json`.
- Published/reference public digest:
  `50374d7472c81cb573f37a2364ac2163e5d230a778bedcffb381d5db3b23aedd`.
- Bundle identity:
  `d2c4cfa95c899e2dfbde81d655463a75897a0dcb8e4e66f3f18ae51cf8490e58`.
- Captured emitter SHA256:
  `84c32d9118ecc86e66147e44eba4b5f1ba2f4b8488e7ed46ba7facc551c9a6cc`.

The actual compile is Icarus `-g2012 -DFUNCTIONAL -s tb` against emitted
**implementation** RTL and both captured stock models. Simulation status is
completed. Both model hashes equal the captured models and owner PDK originals.
There is one actual vvp testbench execution (version probes are recorded separately).
There are no source builds, daemon operations or physical flow/EDA admissions.

To verify persistence independently of FS2 working paths, the harness moves its own
new FS2 request/events/artifact directory to `completed-fs2-transport` after the
provider exits, preserving all evidence. A new public `workload-inspect` process
then reopens the retained result: functional pass, performance available, seven
metrics, exact reference digest and canonical verified bundle locator. The entire
retained closure remains51 hash-inventoried files, unchanged by that reader.

`known-state-before.json` and `known-state-after.json` match: root configs/selected
programs; owner `_flow_results`; owner PT8 workload store; complete old/new selected
generation/provider/config files; and every private captured source hash. Only new
verification evidence and the new private workload closure were added. No old
session mutation or owner daemon stop/restart occurred. Both repositories'
`git diff --check` pass.

Limits: this is the requested one-case direct provider closure check, not a repeat
of Flops, cancellation/negative controls, public API parity, native Testing HTTP or
integrated terminal review. Frontend review evidence is separately documented in
Workbench `docs/pt8_endpoint_independent_review.md`.
