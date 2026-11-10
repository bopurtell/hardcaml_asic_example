# Standalone named-flow client (bounded demonstration)

> **Source-layout note:** the active project CLI is now
> `asics/fifo_demo/cli/project.exe`; see the [layout map](repository_layout.md).
> Retained execution paths and identities below remain historical.

`scripts/headless_flow.py` is a Python-standard-library-only public CLI client.
It imports no provider Python, native private helper, Workbench package, project
source module or Dune module. Dune is needed to build the project executable,
never to run the client. This is one fresh named-flow invocation and its reader;
it is not a scheduler or a Workbench job implementation.

## Frozen-prefix build and checks

This delivery slice uses a new private installation and a freshly linked consumer:

```sh
PREFIX=/tmp/opencode/namedflow-race-provider-v2
export OCAMLPATH="$PREFIX/lib"
dune build -j20 --build-dir _build_namedflow_race bin/project.exe acceptance/export_trace.exe asic_test/catalog_test.exe
HARDCAML_ASIC_TEST_PROVIDER="$PREFIX/bin/hardcaml-asic-flow" \
  dune build -j20 --build-dir _build_namedflow_race @scripts/headless-test
HARDCAML_ASIC_TEST_PROVIDER="$PREFIX/bin/hardcaml-asic-flow" \
  python3 -B scripts/test_project_routing.py _build_namedflow_race/default/bin/project.exe \
    _build_namedflow_race/default/acceptance/export_trace.exe .
python3 -B scripts/check_project_cli.py _build_namedflow_race/default/bin/project.exe
dune exec -j20 --build-dir _build_namedflow_race asic_test/catalog_test.exe
```

These checks do not build/install the provider, refresh the normal selection or
change the recorded pin. Do not run refresh or older scripts which perform nested
provider builds during overlap. The focused alias uses fixture tool outputs and
native readiness checks; supplying the external fixture directory below also
completes native synthesis. All Git mutations are confined to
temporary fixture repositories.

## Direct public flow commands

From the consumer checkout, set absolute roots appropriate to the machine:

```sh
PROJECT="$PWD/_build_namedflow_race/default/bin/project.exe"
PROVIDER=/tmp/opencode/namedflow-race-provider-v2/bin/hardcaml-asic-flow
SOURCE="$PWD"
RESULTS=/tmp/my-flow-results
TOOLS="$PWD/_flow_tools"
"$PROJECT" flow list --json
"$PROJECT" flow describe --flow standard --json
"$PROJECT" flow plan --flow standard --profile balanced --endpoint signoff \
  --source-root "$SOURCE" --json > /tmp/my-flow-preview.json
IDENTITY=$(python3 -c 'import json; print(json.load(open("/tmp/my-flow-preview.json"))["plan_identity"])')
"$PROJECT" flow run --flow standard --profile balanced --endpoint signoff \
  --source-root "$SOURCE" --expected-plan-identity "$IDENTITY" \
  --provider "$PROVIDER" --results-root "$RESULTS" --toolchain "$TOOLS" --timeout 3600 --json
```

The caller must use identical selection/endpoint/typed `--set KEY=VALUE` options
for preview and launch. The project compares the expected identity before
publication or provider launch; source/catalog/Git changes can invalidate it.
Only `flow run` accepts `--timeout SECONDS`, a positive integer execution budget
forwarded to public `stages --timeout` per segment/publication. Omission retains
the native 600-second default. The public provider accepts integer seconds, so
fractions, zero, negative and nonfinite values are rejected. This option is outside
plan content hashing and does not mutate profiles or snapshot identity. Two launch
requests from the same source differing only in budget retain identical plans;
edits to declared source files naturally change source identity.

## Client and reconnect

For terminal physical metrics and optional external acceptance after this client
finishes, see [terminal physical results](#terminal-physical-results-and-acceptance).

```sh
python3 -B scripts/headless_flow.py \
  --project "$PROJECT" --provider "$PROVIDER" --source-root "$SOURCE" \
  --results-root "$RESULTS" --toolchain "$TOOLS" \
  --flow standard --profile balanced --endpoint signoff \
  --stage-timeout 3600 --timeout 7200 \
  --receipt /tmp/my-headless-result.json
python3 -B scripts/headless_flow.py --reconnect --receipt /tmp/my-headless-result.json
```

Omit both selection flags to select the declared catalog default pair; flow alone
selects that entry's default profile. Unknown IDs fail. `--profile` requires
`--flow`. Repeat `--set` for typed request assignments. Optional absolute
`--python`, `--support-tools` and `--pdk-root` override toolchain components.
`--preview-only` saves discovery, description and plan without launching.
`--timeout` retains its overall client budget (default 600 seconds); it is never
forwarded to the provider. `--stage-timeout` is optional positive integer seconds,
forwarded only on launch as project `flow run --timeout`. Omission leaves the
provider's native 600-second budget in effect. For a full fresh six-stage named
flow through signoff, the recommendation is explicit `--stage-timeout 3600
--timeout 7200`, as above; neither recommendation changes a default. The provider
budget is per segment/publication, not a whole-flow deadline. `--poll` controls
the query interval. `--preview-only` retains the same plan under either budget and
records the proposed launch argv without executing it.

Executables and roots must be explicit absolute paths. Invocation uses argument
arrays, no shell, no `resolve`/`normpath` on execution paths: aliases and
symlink-parent/`..` traversal retain kernel semantics. Provider resources are
selected by the explicitly supplied installed executable, with no checkout
fallback. Use the frozen-prefix executable above for this slice.

The client checks provider metadata, discovers the versioned schema, chooses IDs,
describes the selected flow, previews and saves its provider-generated identity,
then launches with the **same** selection/request options plus that expected
identity. It consumes the first JSONL allocation immediately, saves its exact
attempt/stream reference, and polls public `observation read-updates` with stream
and cursor while draining launcher stdout incrementally. Public `observation
inspect` supplies writer/terminal status. Once final, all updates through the
inspected cursor must be read. A zero-exit query is never interpreted as run
success, and inactive writer alone is not a terminal outcome.

The receipt (`example.headless-result`, v1) is a **client-owned cache**, outside
provider results: config, discovery, selected IDs, plan/bundle/methodology
identities inside the retained plan, exact launch argv, raw parsed launcher
messages, allocation paths, updates/cursor, inspection, outcomes and optional
report. Atomic replacement prevents partial JSON; it is not crash-durable storage
or provider authority. One writer per cache; reconnect after stopping the prior
reader, or copy the cache to a distinct filename for a concurrent reader. Never
edit provider truth to match this cache. Reconnect uses only the stored explicit
attempt, stream, cursor and returned references; it does not rediscover/replan.
Config records `timeout` and optional `stage_timeout`, and `launch_argv` records
the forwarded option explicitly. Old v1 receipts without `stage_timeout` default
to no override. Reconnect never launches, reapplies a stage budget or signals a run;
its `--timeout` bounds only the reconnected reader.

Stdout is reserved for protocol output (the client itself prints none); provider
and client diagnostics go to stderr. Exits: 0 execution completed with required
terminal report available (or preview-only), 1 recorded run failure/report blocker,
2 invalid protocol/config/query or missing allocation, 130 client cancellation.
Acceptance is a separate returned result, not implied by allocation, completed
execution or exit 0; `not_evaluated` stays `not_evaluated`.

Ctrl-C/SIGTERM in launch mode forwards SIGTERM to **only its own project/provider
launcher PID** (project dispatch uses exec); after five seconds it kills/reaps that
PID if necessary. Protocol errors/timeouts also clean up that owned launcher.
It does not signal arbitrary process groups or look up other run PIDs. Reconnect
is reader-only: stopping or timing out the reader does **not** signal the run.
Provider cancellation semantics govern any backend children.

Owned cleanup includes reader construction/start and deadline initialization after
launch. Setup failures terminate/reap the child even before allocation is read;
the cache records `client_status: failed` (exit 2) or `interrupted` (exit 130 for
both SIGINT and SIGTERM), `client_error`, and the actual `launcher_exit`.
`reconnect_available` is false when allocation was never received. Cleanup tolerates
an unset/unstarted reader and defers further user signals while reaping. Reader-only
reconnect retains its separate no-producer-signalling behavior.

## Supported versions and provider handoff

The client requires exact integer CLI contract 4 and boolean `namedflow1=true`;
package version alone is insufficient. Discovery/list/catalog/describe and
methodology-plan envelopes are v1, allocation/error terminal envelopes v1,
observation reads/events/inspection v2. CLI4 Runner summaries have no outer version;
the client checks their stage plan v3 and methodology-execution-reference v1,
attempt ID and expected/actual plan identity. Duplicate JSON
keys, nonfinite JSON, malformed required fields and unsupported versions fail.
Additive fields are tolerated. The provider remains responsible for checked plan
hashing, immutable snapshot verification and execution/report validation; this
client never recomputes the OCaml canonical identity in Python.

Named terminal delivery and public inspection now return `execution_file` only
after the provider validates a matching readable persisted record. The client
uses inspection's exact reference, checks any terminal reference agrees, and calls
public `report` on that path. Report schema-1 normalized methodology must match the
preview's plan and bundle identities and allocation's attempt. The delivery field
is not part of the stored Runner schema. No workspace filename reconstruction,
glob, private helper call or current-catalog lookup occurs in the client.

Failed preflight intentionally has `execution_file: null` and client
`report_status: unavailable_no_execution_record`, with client exit 1. A recorded
failed native run has an available report (query exit 0), but client exit remains
1. Execution completion never establishes physical acceptance.

## Native prepared-stage fixture checks

Prepare the external engine fixture once from the provider checkout (test setup
only); pass a support-tools root containing the real pinned TT floorplan DEF:

```sh
python3 -B test/prepare_headless_engine_fixture.py \
  /tmp/opencode/namedflow-delivery-provider-v3 \
  /tmp/opencode/namedflow-delivery-engine-v4 \
  /home/wayne/devel/jane/hardcaml_asic_example/_flow_tools/tt
```

Then from the consumer checkout:

```sh
HARDCAML_ASIC_TEST_PROVIDER=/tmp/opencode/namedflow-delivery-provider-v3/bin/hardcaml-asic-flow \
HARDCAML_ASIC_ENGINE_FIXTURES=/tmp/opencode/namedflow-delivery-engine-v4 \
  python3 -B scripts/test_headless_flow.py \
    _build_delivery/default/bin/project.exe \
    _build_delivery/default/acceptance/export_trace.exe .
```

The original 11 client checks plus the new native integration check exercise real
installed native preparation/Runner/bridge/publication/reporting: balanced and
synth_delay synthesis completion, a failed run with readable report, early
allocation while the external backend is held, reader SIGINT isolation, and
allocation-only reconnect with all terminal stdout discarded. Client runtime has
no Dune on PATH; historical reconnect has PATH/PYTHONPATH denied. Only the external
tool engine is mocked. Fixture setup's inventory helper is not a client dependency.
Discovery, preview, launch, observation and report have **no Workbench dependency**.

## Real two-profile synthesis acceptance commands (next integration)

With the installed prefix and freshly linked executable above, use actual tool
roots, distinct fresh results roots and client cache files:

```sh
PROJECT="$PWD/_build_delivery/default/bin/project.exe"
PROVIDER=/tmp/opencode/namedflow-delivery-provider-v3/bin/hardcaml-asic-flow
TOOLS="$PWD/_flow_tools"
for PROFILE in balanced synth_delay; do
  python3 -B scripts/headless_flow.py \
    --project "$PROJECT" --provider "$PROVIDER" --source-root "$PWD" \
    --results-root "/tmp/namedflow-real-$PROFILE-results" --toolchain "$TOOLS" \
    --python "$TOOLS/.venv/bin/python" --support-tools "$TOOLS/tt" --pdk-root "$TOOLS/pdk" \
    --flow standard --profile "$PROFILE" --endpoint synthesis \
    --receipt "/tmp/namedflow-real-$PROFILE.json" --timeout 1800
  python3 -B scripts/headless_flow.py --reconnect \
    --receipt "/tmp/namedflow-real-$PROFILE.json"
done
```

Inspect each cached report's methodology identity against its preview, explicit
execution reference, completion and separate acceptance. These commands target
synthesis; use the signoff examples and explicit stage/client budgets above for a
full fresh six-stage named flow. The fixture checks establish native orchestration
behavior, not physical acceptance.

## Terminal physical results and acceptance

Run these commands only in the shell responsible for builds and EDA. All paths
below are isolated from the active Workbench config. The installed provider's
public finalization route already supplies normalized terminal timing and
physical checks; see the provider's
[translation contract](../../hardcaml_asic/docs/development/workbench-terminal-contract.md).

If a newly captured provider installation is needed, run from this checkout in
the existing compiler environment:

```sh
SESSION=$(mktemp -d /tmp/opencode/workbench-physical-XXXXXX)
python3 -B scripts/asic_dependency.py --store "$SESSION/provider-store" refresh \
  --source /home/wayne/devel/jane/hardcaml_asic --mode development
. "$SESSION/provider-store/current/activate.sh"
PREFIX=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["generation"])' \
  "$SESSION/provider-store/current/receipt.json")
PROVIDER="$PREFIX/bin/hardcaml-asic-flow"
BUILD="$SESSION/project-build"
dune build --build-dir "$BUILD" -j20 bin/project.exe acceptance/export_trace.exe
PROJECT="$BUILD/default/bin/project.exe"
TOOLS="$PWD/_flow_tools"
"$PROVIDER" --version --json > "$SESSION/provider-version.json"
ocamlfind query hardcaml_asic
```

Refresh builds/installs/probes with `-j20` internally and publishes only this
explicit store's selection. It installs no compiler dependencies and does not
update the normal `.dev/asic/current` or `hardcaml-workbench-asic.sexp`. Set
`SESSION`, `PROJECT`, `PROVIDER` and `TOOLS` explicitly instead if reusing already
validated installed executables; no reinstall is needed solely to collect terminal
physical metrics. Source captures are local receipts, not release stamps.

Fresh physical execution has an explicit two-hour client deadline and a
one-hour per-segment provider budget:

```sh
python3 -B scripts/headless_flow.py \
  --project "$PROJECT" --provider "$PROVIDER" --source-root "$PWD" \
  --results-root "$SESSION/results" --toolchain "$TOOLS" \
  --python "$TOOLS/.venv/bin/python" --support-tools "$TOOLS/tt" --pdk-root "$TOOLS/pdk" \
  --flow standard --profile balanced --endpoint signoff \
  --stage-timeout 3600 --timeout 7200 --receipt "$SESSION/physical.json"
EXECUTION=$(python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["execution_completed"]; print(r["execution_file"])' \
  "$SESSION/physical.json")
"$PROVIDER" report "$EXECUTION" --json > "$SESSION/stage-report.json"
```

On timeout the client terminates/reaps its owned launcher. Reconnect with
`python3 -B scripts/headless_flow.py --reconnect --timeout 120 --receipt
"$SESSION/physical.json"` to inspect the returned allocation; reconnect does not
relaunch or signal the run. An interrupted run is not eligible for finalization.
For an already completed fresh signoff run, use its exact returned execution
reference directly instead of running implementation again.

Collect terminal results with a 30-minute outer deadline (GNU `timeout`):

```sh
timeout --signal=TERM --kill-after=30s 1800s \
  "$PROVIDER" finalize "$EXECUTION" --operation-store "$SESSION/operations" \
  --json > "$SESSION/finalization.jsonl" 2> "$SESSION/finalization.stderr"
OPERATION=$(python3 -c 'import json,sys; rows=[json.loads(s) for s in open(sys.argv[1]) if s.strip()]; print(next(r["attempt"] for r in rows if r.get("event")=="allocated"))' \
  "$SESSION/finalization.jsonl")
"$PROVIDER" finalization-inspect "$OPERATION" --json > "$SESSION/operation.json"
python3 -c 'import hashlib,json,pathlib,sys; r=json.load(open(sys.argv[1])); p=pathlib.Path(r["results"]["path"]); assert hashlib.sha256(p.read_bytes()).hexdigest()==r["results"]["sha256"]; print(p)' \
  "$SESSION/operation.json"
```

Without `--accept`, acceptance remains `not_evaluated`. For full external
acceptance, export the example replay trace, then invoke a separate bounded
finalization operation with all required collateral:

```sh
"$BUILD/default/acceptance/export_trace.exe" > "$SESSION/replay-trace.txt"
timeout --signal=TERM --kill-after=30s 1800s \
  "$PROVIDER" finalize "$EXECUTION" --operation-store "$SESSION/acceptance-operations" \
  --accept --support-tools "$TOOLS/tt" \
  --precheck-python "$TOOLS/.venv-precheck/bin/python" \
  --testbench "$PWD/acceptance/replay.v" --testbench-top replay \
  --replay-trace "$SESSION/replay-trace.txt" --json \
  > "$SESSION/acceptance.jsonl" 2> "$SESSION/acceptance.stderr"
```

Parse that operation's returned allocation and inspect it the same way. Preserve
nonzero exits and inspect the allocated receipt even on timeout or acceptance
failure. Collection results and acceptance are separate facts. Finalization has
no public `--timeout` option; the outer deadline is deliberate. A forced kill
can leave a `running` receipt unresolved, which must not be presented as completed.

Focused provider regression commands, from the provider checkout, are:

```sh
dune build -j20 @test/ocaml-stage-report @test/ocaml-report @test/ocaml-finalization
```

These focused aliases exercise reporting and finalization fixtures. Broad
`runtest` also includes tests that create and commit temporary Git repositories;
select focused checks when the caller requires absolutely no mutative Git.
