# PT.7 timing specimen — preparation handoff

> **Layout note (2026-11-10):** the active timing family now lives under
> `tooling_acceptance/timing/`. See the [layout map](repository_layout.md).
> Commands and source hashes below remain records of the historical execution.

2026-10-28. **Historical preparation handoff.** Subsequent actual bounded
synthesis/STA acceptance is in [pt7_timing_acceptance.md](pt7_timing_acceptance.md),
including the open generated bus-port lookup bug. The remainder records the
earlier preparation state, before completed-provider integration.
The ASIC plan is `../hardcaml_asic/docs/development/pt7-timing-intent.md` relative
to the example checkout. Both public handoffs were read after publication. At
closeout A's handoff still says implementation in progress; B publishes its
schema and A-wire binding but no completed tested-provider readiness statement.
No PT.7 provider was captured from the changing implementation.

## Prepared implementation

* `timing/timing_specimen.{ml,mli}`: three scalar capture registers and a separate
  two-register synchronous control chain. All five have active-low asynchronous
  reset-to-zero. The callback receives actual internal register Q objects.
* `timing/timing_project.ml`: draft integration using **public** `Timing.Stage`,
  `Timing.Exception`, `Timing.create`, and
  `Elaboration.Context.register_timing_stage_exn`. It targets the published A
  contract, but has not compiled against a completed captured PT.7 provider.
  The asynchronous source is exactly `ui_in[0]`, control input `ui_in[1]`;
  `rst_n` targets all five enumerated control pins. Only capture-first D is
  excepted. Outputs have combinational gating to keep Q anchors internal.
* `timing/timing_cli.ml`: thin public `Project.emit_bundle` consumer; prints the
  emitted identity. No consumer-local timing resolver/parser exists.
* `scripts/pt7_tool.py`: exact-local-image, read-only-root, network-disabled tool
  launch with one CPU, one tool thread, 4 GiB RAM, 128 PIDs, 180-second default
  timeout (maximum 600), retained attempts/input hashes and timeout cleanup.
  Synthesis and STA share `/tmp/opencode/example-pt7-sta.lock`. Run sequentially
  with builds to stay within the six-job allocation. This is a launch receipt,
  **not** B's timing-evidence schema or a timing assertion.

## Executed preparation and identities

Observed example base: `6c7e2e281b0ae9a1f1b22074f7e771974819991d`.
New evidence lives only in `acceptance/timing/preparation/`.

```sh
python3 -B timing/check_preparation.py \
  --output acceptance/timing/preparation/core-02
```

This runs exactly:

```sh
opam exec --switch=5.2.0+ox -- \
  flock /tmp/opencode/example-pt7-build.lock \
  dune build --build-dir _build_pt7 -j6 timing/core_test.exe
_build_pt7/default/timing/core_test.exe
```

Both exited zero. Assertions: five scalar callbacks in declaration order; actual
register nodes have asynchronous reset, active-low polarity, constant zero reset
value, no enable or synchronous clear; capture/control output latency is three/two
edges; `Cyclesim.reset` clears both empty and filled pipelines. Cyclesim does not
simulate asynchronous input transitions through ordinary cycle calls: polarity
is a structural assertion, not a simulation claim about reset release.

Core executable SHA-256:
`44a62f64856c4616b2bccb9a988a8b4869d84df6ac157206b15c3805ffb6b307`.
The receipt records every core/prepared integration source hash and raw log hash.
Project source SHA-256:
`841a3c21e3c8573bd81addd80e5cbaec98b2922e4ca4037866c74c441c4350f9`.
Tool launcher SHA-256:
`1cd3fbfbc1e0e5c27e8dde2c105b2a66e9dee6e2aa17ab57b0d2f2d198f0ae94`.

The local image was observed with `docker image ls --no-trunc`, then invoked by
exact image ID:
`sha256:d109140b8f17fc54f4fca998beb8124f4949404ec52e339eebd2250854a18b5a`.
Each of the following was executed separately, sequentially, with full argv,
limits, unchanged-input checks and logs retained under its new output directory:

```sh
python3 -B scripts/pt7_tool.py --tool yosys \
  --work .dev/asic-pt7/tool-probes \
  --output acceptance/timing/preparation/yosys-version \
  --read-only scripts --input scripts/pt7_tool.py -- -V
python3 -B scripts/pt7_tool.py --tool sta \
  --work .dev/asic-pt7/tool-probes \
  --output acceptance/timing/preparation/sta-version \
  --read-only scripts --input scripts/pt7_tool.py -- -version
python3 -B scripts/pt7_tool.py --tool openroad \
  --work .dev/asic-pt7/tool-probes \
  --output acceptance/timing/preparation/openroad-version-02 \
  --read-only scripts --input scripts/pt7_tool.py -- -version
```

Observed: Yosys **0.66**, Git `86f2ddebce7e98ce7cacc27e8a5c14cb53b51b51`;
standalone OpenSTA **2.7.0**; OpenROAD
`dcf36133a369abc8f3c5e5738cd4d82e4903c0e0`.
These were version probes, not synthesis or linked STA runs.

Available typical Liberty (researched, not consumed by timing yet):
`_flow_tools/pdk/ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/lib/sg13cmos5l_stdcell_typ_1p20V_25C.lib`,
SHA-256 `34163f3e7de9f854afac57332ba06f1739b78e7ac35660a8a5ddd39c570124ad`.
A's allowed reset masters are `sg13cmos5l_dfrbpq_{1,2}` and
`sg13cmos5l_dfrbp_{1,2}`, with Q, D, CLK and RESET_B roles. Actual mapping
and pin connectivity remain to be checked on the new synthesis result.

### Retained failures

* First core compilation used the unavailable `reset_edge` label; corrected to
  `reset_level:Low`. `initial-build-failure.json` is explicitly a transcription.
* `core-01`: compiled successfully, simulation exited 2 at edge one because the
  first test wrongly treated the asynchronous port as Cyclesim's reset command.
  Corrected the test to inspect register reset structure and use Cyclesim reset;
  `core-02` passed. Hardware architecture was unchanged by this correction.
* `openroad-version`: initial `-threads 1 -version` returned zero but printed
  usage rather than taking the version-only branch. The launcher now omits
  `-threads` for version-only probes; `openroad-version-02` returned the exact
  version. Real OpenROAD runs retain explicit `-threads 1`.

## Resume once A/B declare readiness

1. Re-read both handoffs, especially integration status and B's exact schema.
   Record handoff/source identities in a new attempt. Capture **then**, not from
   this preparation state. Existing capture implementation runs nested Dune build,
   install, and a public-API link probe sequentially, each with explicit jobs.

   ```sh
   opam exec --switch=5.2.0+ox -- \
     flock /tmp/opencode/asic-pt7-build.lock \
     python3 -B scripts/asic_dependency.py --store .dev/asic-pt7/provider \
       refresh --source /home/wayne/devel/jane/hardcaml_asic \
       --mode development --jobs 6
   ```

   **Important:** preparation scratch currently uses `.dev/asic-pt7/tool-probes`
   without a dependency-store ownership marker. The capture helper refuses any
   existing unowned store. Use a new child store `.dev/asic-pt7/provider` instead
   (`--store .dev/asic-pt7/provider`); do not delete scratch or fabricate an
   ownership marker. The command above already uses that child store. Its
   activation is `.dev/asic-pt7/provider/current/activate.sh`.

2. Source that isolated activation in the 5.2.0+ox shell. Compile the new CLI with
   the example flock, `_build_pt7`, and `-j6`. Fix integration against actual
   public signatures. Only then migrate existing `asic/project.ml` and
   `memory/program_memory.ml` two-field timing literals to `Timing.create` as
   necessary for example regression. Do not migrate historical captured inputs.
3. Emit a **new** bundle using `timing_cli emit SOURCE_ROOT NEW_OUTPUT_DIRECTORY`.
   Retain the complete public manifest, SDC, RTL, source inventory, bundle identity,
   provider receipt and installed executable/library hashes. Bind this emitter's
   compiled-source identity; the preparation core executable is not the emitter.
4. Run bounded Yosys mapping using the actual emitted RTL and copied Liberty,
   retaining the exact script, mapped Verilog and JSON, logs and input/output
   hashes. Verify five distinct actual sequential cells, exact preserved Q nets,
   chain D connections and reset pin roles. `keep=1` is not preservation proof.
5. Run serialized standalone OpenSTA or linked OpenROAD STA, reading the **actual
   emitted SDC once** on the linked mapped netlist. B requires producer tool
   spelling `OpenSTA` with its actual version, even for a linked audit; check
   attribution with B before using OpenROAD. No P&R is allocated.
6. Follow B's schema exactly: `audit.json`, `receipt.json`, all required sources
   (manifest, SDC, netlist, Liberty, driver, log, resolution, exceptions,
   unconstrained, downstream_min, downstream_max, receipt). Print the receipt
   before SDC; print completion only after report generation. Resolve B's apparent
   **driver self-hash issue** before production: receipt inputs include driver
   hash, so the driver must read external receipt bytes, not embed a receipt
   containing its own hash. Retain the actual executed driver and receipt.
7. Extract A's prefixed resolution lines verbatim (line selection only; no local
   timing interpretation). Inspect through B's public CLI/API. Coverage unavailable
   is expected exit 1, not a passing coverage result. Record downstream min/max
   setup/hold paths for both capture links and control link, native unconstrained
   diagnostics and native exception introspection or exact unsupported diagnostics.
   Sampled paths are not exhaustive coverage.
8. New disposable mapped-input/intent negatives: missing anchor, multiple Q
   drivers/ambiguous anchor, wrong mapped pin/master scope, attempted downstream
   capture target, reset/data scope confusion. Require failure before application
   for endpoint failures. Add changed-hash/provenance/truncation negatives through
   B's reader. Preserve each failed run and its exact changed bytes/commands.
9. Run appropriate public-emission/example regressions against the captured
   provider, with explicit `-j6` and example flock. Retain all failures/skips and
   perform independent review as coordinated. Keep each attempt distinct.

## Current limits

Provider-dependent CLI build, fresh bundle emission, real synthesis, linked STA,
stage preservation, downstream min/max path checks, negative tool cases, native
unconstrained diagnostics and B inspection are all **pending/skipped awaiting
tested API readiness**. No timing acceptance, exception-effect coverage, post-PNR
preservation, CDC correctness, metastability/MTBF, reset protocol or Protemu claim
is made by the preparation tests.
