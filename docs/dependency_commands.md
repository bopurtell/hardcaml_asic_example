> **Source-layout note:** commands below include pre-migration paths. Use the
> [layout map](repository_layout.md) and [current README](../README.md) when
> adapting them; recorded installations and results remain historical.

## Current recorded dependency

`asic-dependency.json` now selects committed provider
`4b6bb60562c0133db9e3ccc6b183736e5658a3f0` (2026-11-12). Its committed bytes pass
the installer's read-only renamed API, Project, bundle publication, catalog/plan
and native `flow_cli` ownership checks, including the grouped provider layout.

Check the source without building, installing or selecting a generation:

```sh
python3 -B scripts/asic_dependency.py validate-source \
  --source ../hardcaml_asic \
  --revision 4b6bb60562c0133db9e3ccc6b183736e5658a3f0
python3 -B scripts/asic_dependency.py status --json
```

The source check reports `compiled: false`; it does not certify a fresh installed
package. A later deliberate recorded refresh with `--source ../hardcaml_asic`
and `--jobs 2` requires that exact commit locally, an active compatible OxCaml/Hardcaml
environment, Dune >= 3.17, ocamlfind and the provider's OCaml dependencies
(including Core, Yojson, Cryptokit, Zarith, Spawn and the PPXs). Refresh builds
and installs the captured package in a private generation, checks the installed
interfaces/runtime payload/native helpers, compiles both public-library probes,
and requires exact CLI4 with `namedflow1=true` before publishing `current`.
It does not install missing compiler dependencies or provision EDA collateral.
Run it as a separate operation within the workspace's total 20-job budget.

Read-only checks on 2026-11-12 found Dune 3.24.2 and all the OCaml packages listed
above in switch `5.2.0+ox`. The pinned provider's provisioning script passed
`--check --offline --no-container` against this checkout's `_flow_tools`: support
tools, PDK, LibreLane/precheck environments and environment paths matched the lock.
Container readiness was explicitly skipped; Nix was checked for availability only.
No fresh recorded build, install, compiler probe or EDA run was performed.

Updating the record alone leaves all installed generations, receipts, activation
scripts and Workbench selectors intact. Status can therefore report
`baseline_mismatch` for an older selection; that is expected until an explicit
refresh. In particular, the everyday Workbench launcher retains its separate
generation documented in [workbench_main.md](workbench_main.md#installed-selections-and-persistence).
Even a later `.dev/asic` refresh does not update that launcher selection.

## Development refresh and historical validation

Run from `hardcaml_asic_example` in your existing `5.2.0+ox` shell. After a
development refresh has succeeded, select it **in that same shell**:

```bash
source .dev/asic/current/activate.sh
ocamlfind query hardcaml_asic
python3 scripts/asic_dependency.py status --json
dune runtest . -j 20
```

The query should name `.dev/asic/generations/<selected-id>/lib/hardcaml_asic`,
not `~/.opam/5.2.0+ox/lib/hardcaml_asic`. An unactivated shell can find the old
`0.1.0` package there, causing unbound `Elaborated_project`, `Project.source_inputs`
or `Project.describe`, and rejection of `Project.create ~source_inputs`.
Refresh and bootstrap are child processes; neither can activate your calling
shell. Re-source after refresh or after switching/resetting the opam environment.

To capture current provider edits (including relevant untracked files):

```bash
python3 scripts/asic_dependency.py refresh \
  --source /home/wayne/devel/jane/hardcaml_asic \
  --mode development

source .dev/asic/current/activate.sh
dune runtest . -j 20
```

Refresh bounds its provider build/install and external Dune link probe to `-j 20`.
It publishes a private ignored installation and retains old generations. It
does not change the shared opam installation/pin or `asic-dependency.json`.

The current thin-provider validator requires the native CLI and service helpers,
the full runtime-nine Python payload and all four data files. It no longer requires
installed `cli.py`, `execution_transport.py` or `result_store.py`. Source validation
checks the actual `flow_cli` public executable stanza in `bin/dune`.
Installed Python planner/reader/service imports (including `execution_plan`,
`flow_observation`, `IncrementalReader`) are retired: use native CLI/OCaml APIs.
Optional `PYTHONPATH=/path/to/provider/flow` is deprecated SOURCE-only oracle access,
not installed support. Package 0.1.0 and CLI4 are unchanged only because CLI contracts
are unchanged. The bounded 2026-10-14 validation used a disposable hardlinked prefix
and independent installed-library linkage; it did not refresh the normal selection
or alter the recorded dependency pin.

Historical contract-3 integration verified 2026-10-13: selected generation
`90770d6ce6f04696b3b0082fb3898944`, snapshot SHA-256
`be2db93d3f1b92a8b240167ebadd0b4c0a81484e78356c56cec867f5b19f8e4a`.
After actual activation, library and CLI selected that generation, status reported
`active_is_published` / `active_library_path_is_first` true, and exact
`dune runtest . -j20` passed (18 setup and 11 routing tests, bundle/RTL acceptance).
Provider full forced tests and 53 installed-prefix tests passed. Installed human
and complete JSON inspection of retained placement/observation and accepted
finalization matched domain results; SHA-256 verified 531 retained files unchanged.
The provider's [full closeout](../../hardcaml_asic/docs/development/human-readable-flow-output.md#slice-3--independent-integration-2026-10-13)
records exact paths, commands and output. At that historical validation the
recorded dependency pin was
`1714764859274f80a9f5ad207421a04601824e99`. Re-source in your own shell:

```bash
source /home/wayne/devel/jane/hardcaml_asic_example/.dev/asic/current/activate.sh
```

Current provider interface is CLI contract 4 (package version remains 0.1.0,
persisted records retain their versions). The installer now requires CLI4 plus
the exact boolean `cli_contract.capabilities.namedflow1=true`, along with the
checked catalog, Flow_spec and Methodology_plan APIs. Legacy project dispatch accepts
integer contracts 2, 3 or 4, not arbitrary future versions. The consumer's
`run --endpoint` requires contract 4 before emission; Classic `--stage` retains
its existing behavior on all three. Machine callers must request `--json`;
`stages` journals by default and emits allocation/terminal JSONL, as does
`finalize`. `observation watch` emits reader updates/status JSONL; other observation
queries and inspectors return complete single objects. See the
[ordinary run quickstart](../README.md#explicit-stage-run-and-independent-progress-reader)
and [slice-3 evidence](../../hardcaml_asic/docs/development/flow-journal.md).

## Named-flow consumer validation

The 2026-10-15 consumer-only slice uses a disposable installed-provider capture at
`/tmp/opencode/consumer-namedflow-provider`. It was copied with symlinks dereferenced
from the already-built current provider install tree. No provider source/build was
changed, no normal consumer selection was refreshed, and the recorded pin was not
updated. For this capture, use explicit environment selection rather than normal
activation:

```sh
PREFIX=/tmp/opencode/consumer-namedflow-provider
export OCAMLPATH="$PREFIX/lib${OCAMLPATH:+:$OCAMLPATH}"
export PATH="$PREFIX/bin:$PATH"
ocamlfind query hardcaml_asic
"$PREFIX/bin/hardcaml-asic-flow" --version --json
dune build -j20 @all
HARDCAML_ASIC_TEST_PROVIDER="$PREFIX/bin/hardcaml-asic-flow" dune runtest -j20 .
```

To retain the native fixture's preview, raw JSONL, stderr, launchspec, bundle and
native observation/operation receipts, run the routing tests directly after build:

```sh
HARDCAML_ASIC_TEST_PROVIDER="$PREFIX/bin/hardcaml-asic-flow" \
HARDCAML_ASIC_TEST_EVIDENCE="$PWD/.dev/flow-catalog-checks" \
python3 -B scripts/test_project_routing.py \
  _build/default/bin/project.exe _build/default/acceptance/export_trace.exe "$PWD"
```

It prints the newly allocated `native-namedflow-*` directory, preserving absolute
snapshot/reference paths. `preview.json` is the versioned plan,
`native.stdout.jsonl` is unchanged native output; the `project/_flow_results/`
subtree retains `launchspecs/`, `bundles/`, `observations/` and
`stage-preflight/operations/`.

Verified retained fixture: `.dev/flow-catalog-checks/native-namedflow-6_gl5xg6/`.
Its `preview.json` has plan identity
`2d4b26f5c0a98e9bf34a96b7f716a25e71d83cff8b5dfe85cd5191b0bbd887a3`;
the native stream is `ed478c8f932a4a5797854aca45fe47a7`. Allocation links the pending
snapshot, terminal failure retains the checked reference with SHA-256, and operation
`20261015T005329678798Z_a837080c/operation.json` retains that same reference and
explicit tool roots. The intended fixture failure is collateral revision mismatch,
exit 2, before workspace creation or EDA. All 20 routing tests passed, alongside
20 installer tests, the new catalog test and the existing consumer suites.

Run these sequentially. The explicit test-provider variable enables the installed
native public-CLI fixture: empty temporary collateral and `/bin/false` prevent any
EDA, while the fixture verifies allocation, checked retained snapshot and native
request receipt on the expected readiness failure. Recording-provider fixtures
verify complete fresh dispatch arguments, exact launchspec and bundle association,
unmodified JSONL, exits/signals and lexical executable paths with spaces/symlinks.
Other tests cover pure discovery with empty PATH/invalid Git, profile settings and
different identities with equal generated RTL/SDC, strict overrides/defaults,
stale source/catalog/profile/endpoint/Git context with no output or dispatcher,
capability rejection before publication, and existing legacy commands.

`scripts/asic_dependency.py` now checks current additive Project signatures and
catalog/plan source interfaces; its installed compiler and independent Dune link
probe use the actual public prepare, prepared bundle/plan, discovery and identity
APIs. Normal development refresh remains an explicit separate action using the
commands at the top of this file; a recorded provider without these APIs is
rejected rather than changing the pin or falling back to source.

For manual selection/preview/run commands see
[project-owned named flows](../README.md#project-owned-named-flows-discover-preview-then-run).
Both plan and run require `--endpoint`. Plan stdout is the provider's versioned v1
plan; run requires its `plan_identity` and matching selection/overrides, then uses
the public native `--methodology-plan` launch route. The native early snapshot
links and request receipts are the progress/evidence boundary for a later headless
client; no independent headless client is introduced in this slice.

Contract-4 activation verified 2026-10-13: generation
`f4c4ae2efeec4e34951102587149f4bc`, captured snapshot SHA256
`33468cfda8fb0845310df2ab7409495b324939cf3a51026d5592f3c9fe8f84da`, observed
provider base `31ad2441ac12ce57123a1f37ed5e2bbf5f508d6c`. Status confirmed both active
selection flags; ocamlfind selected this generation. Exact `dune runtest . -j20`
passed, with 14 routing and 18 dependency tests verified, plus existing RTL/bundle
acceptance. The provider fresh installed-prefix suite passed 55 tests before refresh.
One actual `dune exec -j 20 bin/project.exe -- run --endpoint synthesis --json`
completed exit 0; installed watch attached during preparation, stopped with Ctrl-C
without stopping execution, and reconnected after cursor 2 through final cursor 7.
Stream `45fec45f50b5498192de35d79423b9b8`, attempt
`_flow_results/observations/20261013T184318828201Z_45fec45f`. Curated/raw evidence and
bounded source/pin/global-package nonmutation hashes are in the linked feature record.
The receipt names a local dirty development capture, not a release/source stamp;
evidence documentation was added after capture. The recorded pin remains unchanged.

Historical recovery verified 2026-10-13 (before CLI contract 3): development refresh published generation
`8e42b6dd928842c9b3865b75497ff063`, with receipt at
`.dev/asic/current/receipt.json`. It captured dirty provider bytes at observed
base `ebdcfbfec88cc05f433bec8d289d98b7ad76d4cf`, snapshot checksum
`1ad6407097657acd7160080a7b27a96e0012b753d2703e77e1689d571c96fa4c`.
After activation, library and CLI resolved that generation; exact
`dune runtest . -j 20` and `dune build @all -j 20` exited 0, including compilation
of the stage-recipe companion. These are local receipt facts, not a release stamp.

Recorded mode selects exactly the revision in `asic-dependency.json`, now
`4b6bb60562c0133db9e3ccc6b183736e5658a3f0`. The former `171476...` pin lacked the
required Project API; the current committed source passes that gate. A fresh
recorded installation still requires the build/link/runtime validation described
above. To explicitly install and select it later:

```bash
python3 scripts/asic_dependency.py refresh \
  --source /home/wayne/devel/jane/hardcaml_asic \
  --mode recorded --jobs 2

source .dev/asic/current/activate.sh
```
