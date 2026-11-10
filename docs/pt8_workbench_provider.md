# PT.8 Workbench provider handoff (C)

**Standard ASIC flow recovery:** the historical config-only sessions below support
the tested PT8 path but lack the FIFO source closure needed by ordinary ASIC Plan
and Fresh preparation. New source-complete private session
`session-standard-recovery-02` passes14 standard native HTTP Plans, real emit and
Fresh source build/emission with no physical launch. See
[`pt8_standard_plan_recovery.md`](pt8_standard_plan_recovery.md) for the bounded
plan, exact receipts/failures, two-job build policy, and new review launch pair.
The running `session-final-review-01` config/provider/pair remains unchanged.

**Current status: final real native HTTP/PTY acceptance PASS** on
`session-final-review-01`, evidence
`native-acceptance-bb8eac43b648403d86e6c94c5cc9dfe3`. Production Testing form →
fresh Exact implementation RTL → available FS2 reference artifact → exact
digest-pinned Validated Workloads inspection is verified. Original sim04 A/B
automatic bundle capture and seven zero deltas are verified. Historical blocked
attempts below remain as evidence; the final acceptance section supersedes them.
The latest extension also automatically recaptures the fresh Exact result as B
and compares it with original sim04 Flops A: seven comparable zero deltas.

Frozen FS2v1 interface, 2026-11-05:

- Suite: `pt8-memory-workloads`.
- Cases: `flops256`, `exact256` (either or both, sequential).
- Seed: decimal `34097` (`0x8531`) only. This is a declarative identity of
  the existing fixed directed stimulus, **not** a parametric random generator.
  Every other seed is rejected before Started or producer execution.
- Parameters: empty. ASIC inputs: empty. Unsupported fields/options rejected.
- Artifact IDs: `flops256-result-reference`, `exact256-result-reference`.
  Kind `json`, media type `application/json`. Each contains exactly
  `{"contract":"hardcaml-workbench.pt8-result-reference","schema_version":1,
  "result":"/absolute/retained/result.json","source_digest":"<public inspect digest>"}`.
- Provider: new `scripts/pt8_workbench_provider.py`; producer helper:
  `scripts/pt8_workbench_runner.py`. Both use the real example producer root.
- Retention: unique directories under `.dev/asic-pt8-workbench/workloads`,
  outside FS2 temporary work. Full bundles, implementation RTL, stock models,
  stimulus, trace, simulation/result records, commands and logs are retained.
- No build during provider execution. Setup captures an isolated ASIC install
  after workload-inspect is available and prebuilds the example emit helper in
  `_build_pt8_workbench`. Runtime children stay foreground in FS2's process group.
- Failed/partial public inspections remain readable (exit0); invalid evidence
  is exit2. Successful FS2 cases require a functional pass and publish an exact
  reference only after public inspection succeeds.

Private setup/launcher and native acceptance commands/results will be appended
here once exercised. Root FIFO/PT6 configs and existing provider pointers are
not used as install destinations.

## Initial availability (for A/B)

The public command/capability is implemented and built. An isolated installed
capture is available under
`.dev/asic-pt8-workbench/session-c-initial-02/asic/generations/007825ac102c45cf8d404bd53f09e00b`.
Its configured project is `session-c-initial-02/project` (relative to the same base).
Direct acceptance `session-c-initial-02/direct-acceptance-ff71dcabb2654e469cceb1259961ae71`
ran both real positive cases and public CLI/API parity, seed/options rejection,
partial-case artifact suppression and actual native-child cancellation/reaping.
During protocol review the cancellation event was corrected to FS2 `Incomplete`
(there is no provider `Cancelled` outcome; cancellation lifecycle belongs to FS2).
Use the next corrected immutable session for integration; initial capture retained.

## C initial pass / integration handoff

Use the current private session (absolute base is
`/home/wayne/devel/jane/hardcaml_asic_example/.dev/asic-pt8-workbench`):

- Session: `session-c-native-04`.
- Private project: `session-c-native-04/project`.
- ASIC immutable generation:
  `session-c-native-04/asic/generations/5e32f035e347413c8ee2b860584ea91d`.
- Provider prefix and exact captured source/binary/model hashes:
  `session-c-native-04/manifest.json` and `provider-command.json`.
- Passing direct acceptance:
  `session-c-native-04/direct-acceptance-8e376ec373254e91a0fb28420edd5468/assertions.json`.
- Public CLI tests (including read-only strace, positive/failure/partial public API
  parity, invalid evidence and strict arguments): `cli-parity/assertions.json`
  inside that acceptance directory. ASIC test entry is
  `hardcaml_asic/bin/workload_inspect_acceptance.py`.
  The strict CLI suite passed 33 native commands.
- Each actual execution has a new retained directory in `workloads/`, including
  `outcome.json` and a hash/byte inventory. Invalid seeds/options create none.
  Missing-model negative retains the successful Flops reference, suppresses the
  failed Exact reference, and preserves partial Exact evidence. Cancellation
  signals a running native child, reaps it, retains cancelled evidence, publishes
  no result artifact, and emits protocol-valid `Incomplete` with exit130.

Commands run from the real example checkout:

```sh
opam exec --switch=5.2.0+ox -- python3 -B scripts/pt8_workbench_setup.py \
  --session session-c-native-04
python3 -B scripts/pt8_workbench_acceptance.py \
  --session .dev/asic-pt8-workbench/session-c-native-04
```

Setup takes the shared ASIC lock across **all** nested Dune build/install/probe
commands, each explicitly six jobs with `_build_pt8_workbench`. Example prebuild
uses its shared lock with the same build name. Configured execution builds
nothing. Captured provider scripts, binaries, stock models and private configs
are read-only files. New setup requires a new session name; no existing configured
generation is overwritten. The private launcher also installs a session-only Dune
budget shim for stock Workbench project probes/actions (six jobs, new build dir,
example lock); `--version` is only a version probe. EDA allocation remains zero.

### Launch pair once A/B prebuilt mains are ready

Run these in separate foreground terminals, from the real example checkout:

```sh
opam exec --switch=5.2.0+ox -- python3 -B scripts/pt8_workbench_launch.py daemon \
  --session .dev/asic-pt8-workbench/session-c-native-04
opam exec --switch=5.2.0+ox -- python3 -B scripts/pt8_workbench_launch.py client \
  --session .dev/asic-pt8-workbench/session-c-native-04
```

The launchers use only Workbench's prebuilt
`_build_pt8_workbench/default/daemon/main.exe` and
`_build_pt8_workbench/default/terminal/main.exe`, private discovery/state/client
state, and the private configured project. The daemon stays foreground. No
automatic launch/restart of a live daemon occurs. From the palette open Workloads,
or launch the fresh workload through Testing's suite/subset form. Reference IDs
above are exact, case-specific artifacts; FS2 attempt IDs are not PT8 simulation
attempt IDs or bundle identities.

### Native HTTP/PTY integration status

Prepared entry point:

```sh
opam exec --switch=5.2.0+ox -- python3 -B scripts/pt8_workbench_native_acceptance.py \
  --session .dev/asic-pt8-workbench/session-c-native-04 \
  --direct-acceptance .dev/asic-pt8-workbench/session-c-native-04/direct-acceptance-8e376ec373254e91a0fb28420edd5468
```

It owns one private foreground daemon, uses native HTTP to inspect/compare the
real positive pair, inspect a readable failed result, discover/launch both fresh
cases, fetch reference artifact bytes and import with the public digest, then
attaches the production terminal in a wide/narrow PTY. It retains HTTP and PTY
captures and shuts down only its own daemon.

Initial invocation was blocked before daemon launch: A/B's prebuilt
`_build_pt8_workbench/default/daemon/main.exe` was not present. Therefore HTTP/PTY
and user-form end-to-end acceptance are **pending**, not claimed by the passing
direct provider tests. Main/coordinator independent review is still required.
No physical qualification or physical winner is asserted.

The configured private Dune shim was exercised directly with the real switch:
`describe workspace --root . --format=sexp --lang=0.1` succeeded and reported
`_build_pt8_workbench/default`. Final `git diff --check` passed in ASIC/example;
the example's pre-existing tracked diff remains `acceptance/dune` and
`asic/project.ml`. C's example changes are new files only.

## Real native integration follow-up (A/B mains available)

Both prebuilt mains were verified executable before launch. C changed only its
example acceptance/launcher harness. The private launcher now creates its own
`discovery`/`state` directories before exec (the first attempt exposed that harness
omission, retained as `native-acceptance-6c48210e1b14461b9a9dea4d42405132`).

Actual native HTTP plus basic wide/narrow PTY passed:
`session-c-native-04/native-acceptance-58241c3efced49e5a8ed97a0708cbf39`.
It checked the real retained pair's seven zero deltas and exact throughput delta,
readable failure with unavailable performance, fresh Flops/Exact FS2 execution,
native artifact byte RPC and digest-pinned workload import.

Extended **production UI form** acceptance:
`session-c-native-04/native-acceptance-7083fd38852b4f1c8802029c1d688506`.
`reviewed-summary.json` summarizes retained actual wire/PTY evidence without
executing anything. Observed gates:

- Workloads imports real retained Flops/Exact, captures the explicit bundles,
  selects `resource_policy`, and displays all seven comparable zero deltas.
  `ui-comparison-04.txt` shows all seven metrics and exact throughput delta0/1.
- Readable functional failure is displayed in Workloads.
- Three warm ASIC Gets, filtering, warm reopen and 80/150-column resize execute
  **no subprocess at all**, checked against the private daemon's process trace.
- The production Testing form was opened through **Workloads: Launch fresh PT.8
  workload**, case changed to `exact256`, seed34097 accepted, final `launch`
  confirmed. Native FS2 attempt
  `sim-70f81d21d043dd321a5bdb47d5ef34a1bc6dec9fa0b9ed7ae4438c8b338e4ad8`
  completed `Passed`. This is actual implementation RTL with the captured stock
  models, not an HTTP-submitted substitute for the UI launch.
- **Blocked A defect:** after choosing exact256, **Inspect workload result
  (selected Testing case)** is absent (`No matching commands`). Native FS2's
  available artifact ID is
  `sim-70f81d21d043dd321a5bdb47d5ef34a1bc6dec9fa0b9ed7ae4438c8b338e4ad8-exact256-result-reference`.
  `terminal/testing_workspace.ml`'s `workload_artifact` tests only the bare
  provider event IDs `flops256-result-reference`/`exact256-result-reference`.
  The real public FS2 artifact ID is attempt-prefixed. C does not bypass this
  UI admission in the harness. Full UI result handoff remains failed/pending A.

The provider event IDs frozen above are unchanged; they are not the native
attempt-prefixed artifact transport IDs. The native harness uses the actual ID
when reading artifact bytes, as required by the frozen FS2 protocol.

### Usability observations for main review

1. The missing artifact action above blocks the advertised completion path even
   though the case and artifact are valid. It needs A correction and a real rerun.
2. Bundle capture requires long manual absolute paths. The current inspection
   projection exposes identity, not a locator. The reference artifact's exact
   four-field schema is frozen; C has not added a bundle locator. A public-reader
   locator/schema change requires the main owner's decision.
3. The selected-subset launch wizard correctly executes only exact256, while the
   catalog still shows its original two selected cases after launch. The form's
   confirmation/captured-case detail is correct, but users must distinguish catalog
   selection from the completed attempt's captured selection.
4. Long absolute paths and full reader/capture identities consume several screens
   before comparison metrics. The seven zero deltas required scrolling; raw ANSI
   and screen captures are retained for review.

### Preservation and provenance

Both native runs retained `root-protected-before.json` / `root-protected-after.json`.
All existing root `hardcaml-workbench*.sexp`, dependency record, and their selected
provider/project executable hashes and symlink targets matched. The configured
PT8 provider's source/binary/model hashes still matched the immutable setup
manifest. Only each test's own private daemon was started and stopped; no live/root
daemon restart, root config/provider adoption, EDA invocation or root build occurred.
The process trace and exact Workbench binary hashes are retained per run.

Rerun after A fixes/builds its slice using the same documented native acceptance
command. The extended harness records each gate as it passes and requires the UI
artifact handoff to create a Validated Inspect query with the reference's exact
expected digest; it will not mark the full run passed without that gate.

Final read-only installed/root audit:
`session-c-native-04/final-audit-72f3422b97ee47bdaf7a8223e82350e0`.
`installed-final.json` inventories the entire captured ASIC generation, FS2
provider, private configs and Dune shim. `assertions.json` confirms the root
configuration/selected binaries still match the extended run's initial baseline,
and the immutable FS2 provider still matches setup's captured manifest. Final
ASIC/example `git diff --check` passes. This audit launches no daemon/tool/build.

## Additive public bundle-locator prerequisite (coordinator-authorized)

The public workload inspection now emits `binding.bundle`: the absolute canonical
selected root used by the existing bundle verifier. `binding.bundle_identity`
remains the exact identity. This is a descriptive verified-root locator for
automatic A/B capture, not a new identity or authenticated-execution claim.
Retained result/simulation records and the exact four-field FS2 reference schema
remain unchanged. The fresh inspection digest covers the additive locator;
historical provider/source digests must not be rewritten or relabelled.

Focused ASIC result/comparison suites passed (51 result API checks, 49 comparison
API/CLI checks, 39 late-fence checks, plus directory/descriptor regression). Tests
verify the locator equals the selected verified bundle, including canonicalization
through a published-root symlink, and that comparison-side nested inspections
retain it with the original bundle identities. B's existing backend workload suite
passed 63 checks with legacy synthetic projections omitting `binding.bundle`.

New immutable capture is `session-final-review-01`; use it rather than
`session-c-native-04` for the locator-aware full native rerun after A is ready.
Previous captures and all prior execution/reference identities remain intact.

Installed ASIC generation:
`session-final-review-01/asic/generations/ee3af8de9f83418b9afed9c67e473e3c`.
Passing fresh direct-provider acceptance:
`session-final-review-01/direct-acceptance-411b32f421f54fe4a85e9aec72dffbc2/assertions.json`.
Both real positive cases and their installed CLI/API checks now additionally
assert `binding.bundle` equals the selected verified canonical bundle root, with
the exact manifest identity preserved. All prior seed/cancel/partial/stock-model/
artifact/reference/read-only CLI checks passed again against this new capture.

Actual setup/direct commands, from the example checkout:

```sh
opam exec --switch=5.2.0+ox -- python3 -B scripts/pt8_workbench_setup.py \
  --session session-final-review-01
python3 -B scripts/pt8_workbench_acceptance.py \
  --session .dev/asic-pt8-workbench/session-final-review-01
```

All nested ASIC Dune calls used the shared ASIC lock, six explicit jobs, and
`_build_pt8_workbench`; the example prebuild used its shared lock with the same
budget/build name. No root configs/provider pointers were adopted, no retained
records were rewritten, and no live daemon was started/restarted for this step.
Full native UI rerun intentionally awaits the coordinator's A-ready request.
Final audit is retained at
`session-final-review-01/final-audit-afde70764e164ce686373dc92277211e`:
root config/selected provider fingerprints unchanged, immutable FS2 capture
matches setup, current reader source matches the captured ASIC source, and the
full installed-generation/private-config inventory is retained. ASIC receipt
SHA256: `12485d394046661f9571e4d6144bfe666fac45fb6f0ef11468b6445894f2732d`.

## Final real HTTP/PTY acceptance — first PASS

2026-11-05, after A's F1–F4/automatic-capture and B's cache corrections. Both
`_build_pt8_workbench/default/{daemon,terminal}/main.exe` were checked executable
before starting. No Workbench source was changed or rebuilt by C for this run.

Run from `/home/wayne/devel/jane/hardcaml_asic_example`:

```sh
opam exec --switch=5.2.0+ox -- python3 -B scripts/pt8_workbench_native_acceptance.py \
  --session .dev/asic-pt8-workbench/session-final-review-01 \
  --direct-acceptance .dev/asic-pt8-workbench/session-final-review-01/direct-acceptance-411b32f421f54fe4a85e9aec72dffbc2
```

Passing evidence directory (relative to the same private session):
`native-acceptance-27e51bb7f0e6461faa836ed64b363d02`.
`assertions.json` records the complete passing gates. `invocation.json` records
the exact harness command/cwd; `http.json` and `process.strace` retain actual native
wire/process evidence. Per-step `.txt`/`.ansi` files capture the production client.

### Observed passing gates

1. Fresh public reader inspections of the **original**, unmodified
   `acceptance/pt8-workloads/simulation-04/{flops,exact}/result.json`, using the new
   installed reader/source digests. `retained-fresh-reader.json` captures those
   projections. Original result/simulation records, RTL/models and bundles were
   hashed before and after: identical bytes; no original identity was rewritten.
2. Public/native retained comparison: seven comparable zero deltas, exact
   throughput delta0/1. Workloads imports the same original pair, captures A/B
   immediately with no manually entered bundle path, and sends the exact verified
   locators plus both freshly captured workload digests. See
   `ui-auto-capture-pair.json` and `ui-comparison-04.txt`. The latter shows all seven
   metrics, outcomes, exact ratio and physical qualifications together.
3. Readable functional failure displayed with unavailable performance. Warm ASIC
   Gets, filtering, reopen, and 80/150-column resizing launch **no tool**, checked
   against the private daemon's actual process trace.
4. Native HTTP fresh Flops/Exact execution passes, including available reference
   artifact byte retrieval and expected-digest inspection.
5. **Production Testing form submission**: open through Workloads' fresh-launch
   command, choose `exact256`, accept seed34097, confirm `launch`. The new actual
   implementation-RTL/unchanged-stock-model run completes Passed. See
   `ui-form-{cases,seed,confirm}.txt`, `ui-fresh-finished.txt`, and
   `ui-completed-attempt.json`.
6. Select exact256 and invoke **Inspect workload result (selected Testing case)**.
   The available attempt-prefixed artifact now resolves correctly. Workloads opens
   with `Validated`, functional pass and performance available. The published cache
   query contains the exact retained result path and the reference's expected
   digest; selected JSON has that same digest. See
   `ui-artifact-workloads-handoff.txt` and `ui-handoff-cache.json`.

### Distinct provenance identities

- Installed provider generation remains
  `ee3af8de9f83418b9afed9c67e473e3c` (captured during setup, not a run ID).
- Its receipt SHA256 remains
  `12485d394046661f9571e4d6144bfe666fac45fb6f0ef11468b6445894f2732d`.
- Native HTTP FS2 attempt:
  `sim-f6e4722946e2e0fb5659140ad8c68de08d8fc4dce751d962d04f3bcfb28ebcab`.
- Production UI FS2 attempt:
  `sim-080046fd44a65407b1b4c06535452f4296671a901c32d691f3be803b1f1315e6`.
- New PT8 simulation attempt: `exact-e8027e305734432bb90067759f6cfa2a`.
- Its exact result is
  `.dev/asic-pt8-workbench/workloads/exact256-175df32e07d74ccab0a1e13e7c833238/exact/result.json`;
  public digest
  `d2b75076dc135c18e5255a66900abfdade6d264a00312ba1d340fdbdb396d1ca`.
- Original sim04 attempts remain
  `flops-5f61451373a0449fb9c52fa2bdbe51f2` and
  `exact-de87619a9bcc415482afb8ee18d09fdc`. New inspection does not relabel their
  original simulation producer as the newly captured reader.
- Workbench daemon SHA256:
  `ec0108fd3ae65ac8bc8113462bfc1eb4dcdcbecf6410c144fbc982113f495a38`;
  terminal SHA256:
  `43740a9dcdd1a23f39ab2d4837f1cb570251c4a4910c862906dd001c462d2c46`.
  Both remained unchanged during the passing run. Installed inspection/comparison
  companion hashes are also recorded in `assertions.json`.

### Failed attempt retained; harness correction

`native-acceptance-b0a266d4dbc14516a3168a291a422932` failed because C's harness
expected full capture/source-digest rows in A's newly concise default detail view.
Automatic capture itself did not require a bundle form. The harness was corrected
to assert production summary display, absence of a bundle-entry form, and the
actual backend comparison locators/digest pins. It also recognizes the new compact
single-line metric rendering. No backend/UI behavior was bypassed or changed.

### Final preservation audit and launch pair

The passing run's root-config/selected-provider, full installed-generation/private-
config, original retained-evidence/bundle, and Workbench-binary before/after checks
all pass. Final read-only audit:
`final-audit-6a739e0ab6fd4d25a5ba95fc4b10d063`. It retains final full installed
inventory and root hashes. ASIC/example `git diff --check` passed. EDA allocation0;
no root build/config/provider adoption or external feature daemon mutation.
The acceptance owner stopped only its own private daemon and terminal.

User launch pair, separate foreground terminals from the example checkout:

```sh
opam exec --switch=5.2.0+ox -- python3 -B scripts/pt8_workbench_launch.py daemon \
  --session .dev/asic-pt8-workbench/session-final-review-01
opam exec --switch=5.2.0+ox -- python3 -B scripts/pt8_workbench_launch.py client \
  --session .dev/asic-pt8-workbench/session-final-review-01
```

These use the private project/discovery/state and the prebuilt Workbench mains.
On a new daemon, retained workload caches correctly begin unverified until explicit
refresh; durable Testing history and result closures remain available. The warm
filter test left `no-match` as a saved filter; clear it (`/`, Ctrl-U, Enter/Esc) when
returning to the results list. The selected fresh result remains inspectable.

## Extended final native PASS — retained plus freshly UI-launched comparison

The same documented native command was extended with one additional acceptance
gate: after the successful UI artifact handoff, **explicitly recapture fresh Exact
as B**, leave retained original sim04 Flops A intact, and query `resource_policy`.
This verifies a fresh-vs-retained comparison as well as the required original pair.

Latest passing run:
`session-final-review-01/native-acceptance-bb8eac43b648403d86e6c94c5cc9dfe3`.
All gates from the first pass above passed again, including exact expected-digest
handoff and every preservation check. Additional evidence:
`ui-fresh-vs-retained-comparison.{txt,ansi,json}`. All seven workload deltas are
comparable zero; the right nested workload digest and simulation attempt are
exactly the new result's, while left remains original sim04 Flops. No new manual
bundle path was entered. `assertions.json` records
`ui_fresh_exact_vs_original_flops_seven_zero_deltas=true`.

Latest distinct identities:

- Installed provider generation/receipt and Workbench binary hashes remain the
  same as the first pass above; no recapture/relabel occurred between attempts.
- HTTP FS2 attempt:
  `sim-6c0229b8f7045b221a51f94b1fb52e9b29c7a738cba26e3fff42e91e78052044`.
- Production form FS2 attempt:
  `sim-10e4dc7a9cba33a5ed690e880e059fdaada9dcd2c3ee1786de3471d30517e8e5`.
- New PT8 simulation attempt: `exact-c5cf64b87a1741d69c76793e2af8130d`.
- New exact result:
  `.dev/asic-pt8-workbench/workloads/exact256-85ad49b3188740e480231d4ff47d0f39/exact/result.json`.
- Exact public inspection/reference digest:
  `9c2c7a83b1a316c98aece1739dd2a1a5f929829006eff8b56ea4202548dda11a`.

Latest read-only audit:
`session-final-review-01/final-audit-a97dcfe970a4461a8e3dec9e0ebb8cf4`.
Actual command:

```sh
python3 -B scripts/pt8_workbench_native_acceptance.py --audit-only \
  --session .dev/asic-pt8-workbench/session-final-review-01 \
  --baseline-evidence .dev/asic-pt8-workbench/session-final-review-01/native-acceptance-bb8eac43b648403d86e6c94c5cc9dfe3
```

Root configurations/selected providers, the full installed generation/private
configs, original sim04 evidence/bundles, and the prebuilt Workbench binaries
matched before/after. Current reader source still matches captured source. Final
`git diff --check` passed in ASIC and example. The user launch pair above uses
this same final private session; no acceptance-owned daemon is left running.
