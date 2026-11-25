# Run the FIFO flow without a workbench

The Python-standard-library client `scripts/headless_flow.py` uses only public
project and installed provider CLIs. No Silver, SDK, sibling checkout or private
provider helpers are needed. Follow steps 1–2 of the [README](../README.md)
first, in the same compiler environment. The provider must advertise CLI
contract 4 and `namedflow1: true`. The client reads the current stage-plan schema
4 as well as historical schema 3.

## 1. Select executables and preview a synthesis plan (PDK-free)

From the example root, in Bash:

```sh
PROJECT="$PWD/_build/default/asics/fifo_demo/cli/chip.exe"
PROVIDER=$(command -v hardcaml-asic-flow)
TOOLS="$PWD/_flow_tools"
mkdir -p _flow_results
SESSION=$(mktemp -d "$PWD/_flow_results/headless.XXXXXX")
python3 -B scripts/headless_flow.py \
  --project "$PROJECT" --provider "$PROVIDER" --source-root "$PWD" \
  --results-root "$SESSION/results" --toolchain "$TOOLS" \
  --flow standard --profile balanced --endpoint synthesis \
  --receipt "$SESSION/preview.json" --preview-only
```

The preview records the catalog, chosen profile, bundle and plan identities.
It launches no EDA or provider execution. Receipts are client-owned caches,
not authoritative provider records. Use distinct receipt paths for distinct
runs. All executable and root arguments must be absolute paths.

## 2. Provision and run actual synthesis

Install Docker and ensure it is usable as your current user. Provision the
provider's pinned IHP PDK, TT support tools, LibreLane runtime and image:

```sh
./bootstrap.sh --toolchain "$TOOLS"
./bootstrap.sh --toolchain "$TOOLS" --check
python3 -B scripts/headless_flow.py \
  --project "$PROJECT" --provider "$PROVIDER" --source-root "$PWD" \
  --results-root "$SESSION/results" --toolchain "$TOOLS" \
  --flow standard --profile balanced --endpoint synthesis \
  --stage-timeout 3600 --timeout 7200 --receipt "$SESSION/synthesis.json"
```

The client previews again at launch and submits the exact expected plan identity.
The provider allocates an attempt and returns its observation stream. The client
reads updates and terminal status, then queries the returned execution record.
The stage timeout is a positive integer number of seconds per provider segment;
the client timeout is an independent whole-client deadline. Set both explicitly
for long runs. To run a different profile, use `--profile synth_delay` with a
new results directory and receipt. For a full implementation, use `--endpoint
signoff`, not just synthesis, and a new receipt/results directory.

## 3. Inspect and reconnect

```sh
python3 -B scripts/headless_flow.py --reconnect --timeout 120 \
  --receipt "$SESSION/synthesis.json"
EXECUTION=$(python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["execution_completed"]; print(r["execution_file"])' "$SESSION/synthesis.json")
"$PROVIDER" report "$EXECUTION" --json > "$SESSION/report.json"
```

Keep the exact returned execution path; do not guess filenames based on stage
or run IDs. A completed execution and readable report are not signoff acceptance.
Synthesis is only the first implementation boundary. The client's exit 0 means
preview succeeded or execution completed with the required report; exit 1 means
recorded failure/report blocker, 2 invalid protocol/config/query or missing
allocation, 130 interrupted. A failed run may still have a report; a failed
preflight may have none. Inspect the receipt even after a nonzero exit.

Reconnect is reader-only, requires a recorded allocation, and resumes from the
stored cursor. Stop the previous receipt writer first or use a distinct copy of
the receipt. Reconnect does not launch, replan or signal the producer. Interrupting
launch mode terminates its own launcher; interrupting reconnect does not.

## 4. Direct CLI alternative

For callers that want raw launch JSONL rather than a client receipt, use the
same public contract. Keep all selection options identical between plan and run.

```sh
"$PROJECT" flow plan --flow standard --profile balanced --endpoint synthesis \
  --source-root "$PWD" --json > "$SESSION/direct-plan.json"
IDENTITY=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["plan_identity"])' "$SESSION/direct-plan.json")
"$PROJECT" flow run --flow standard --profile balanced --endpoint synthesis \
  --source-root "$PWD" --expected-plan-identity "$IDENTITY" \
  --provider "$PROVIDER" --results-root "$SESSION/direct-results" \
  --toolchain "$TOOLS" --timeout 3600 --json > "$SESSION/direct-run.jsonl"
```

Source edits, catalog changes and Git HEAD changes can invalidate the preview.
The first allocation identifies the exact observation stream; use provider
`observation inspect` and `observation read-updates` for live queries. Run and
query exits are distinct. Do not treat a zero-exit query as run success.

## 5. Collect signoff results separately

For a **completed signoff** run (not the synthesis receipt above), take its exact
execution reference and invoke `hardcaml-asic-flow finalize "$EXECUTION" --json`.
Finalization collects terminal physical metrics; external acceptance additionally
requires `--accept` and the relevant replay/precheck collateral. See the installed
provider's `finalize --help`. Neither collection nor synthesis alone establishes
physical acceptance.
