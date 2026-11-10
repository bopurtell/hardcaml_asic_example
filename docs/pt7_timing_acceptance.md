# PT.7 independent example: actual bounded synthesis and STA

> **Historical execution record:** active timing source is now grouped under
> `tooling_acceptance/timing/`. See the [layout map](repository_layout.md).

**Final-candidate update:** actual corrected bit and scalar native acceptance is
complete in [pt7_timing_final.md](pt7_timing_final.md), with native coverage still
unavailable. The results below remain the original provider's historical scalar
acceptance. Intermediate r2 failures are in [pt7_timing_corrected.md](pt7_timing_corrected.md).

2026-10-28. **Scalar-source acceptance executed. Bus-bit source exposed an open
library/tool-compatibility bug. Native coverage remains unavailable.**

This is a new standalone synthesized-netlist audit, unrelated to historical SRAM
timing or physical producers. Raw evidence is under `acceptance/timing/`. No P&R
was launched. See [the source finding](pt7_timing_findings.md) for A-REAL-1 and
[the earlier preparation](pt7_timing.md) for its retained failures.

## Exact identities

| Identity | Value |
| --- | --- |
| Provider generation | `.dev/asic-pt7/provider/generations/da135e7054a3454fa0d822e86d0973bc` |
| Observed provider base | `e46bfd7609e0b119ad74a8b412a3e866da5297de` |
| Provider source SHA-256 | `fab4b4a6d46ca47cf9ee721b16df70081dbf5590f42ae8938e17391c6acc4b43` |
| Provider receipt SHA-256 | `7adcacd4c8ac23190f7924780f3588c5d494ce28f965b33277b2e0a864e0d617` |
| Dispatcher SHA-256 | `0282e2805d2d5f9f424d8ab006fc313cc8ac1e97a1c6ed9f58fad8ce5f1f8a3b` |
| Native timing-inspector SHA-256 | `a4ef2cf2578f0d8f97cd98682e3494841db96f8dc8011e7f824143e77259693f` |
| Emitter SHA-256 | `908d2585a00dc8c5601142c7a9ff0727583d8c03a24d382d403f177de8be5eb7` |
| Scalar bundle identity | `d0e2dc93adb696304e5529aff6df4590d8beb238315b59322d8fb87719827027` |
| Accepted audit ID | `sta-scalar-02` |
| Audit JSON SHA-256 | `9d44db3dc0ccca7bc314091e6558de11ae2df45b090f6eee9b10dc2b1a41bce1` |
| Audit receipt SHA-256 | `bbbfc4dfb8cfddc9225edb5046b105579a518b741b4db222375e47809f90394d` |

This is a local dirty development capture, not authenticated execution or a
clean-source/P6 stamp. `closeout-01/producer-identities.json` records every installed
binary/library archive and emitter compiled artifact hash. The retained full
bundle is `synth-scalar-01-bundle/`; manifest file/source digests are verified.

| Linked input | SHA-256 |
| --- | --- |
| Manifest | `a3f52d58804feaefe4a64de08e7b9c84957d5e83be6841129cd8aa80b1416c56` |
| Unmodified emitted SDC | `e69f0b8f6b762eed5364cdd5f8d85294be5ddf06882463d2953c2d62f2077e96` |
| Mapped Verilog | `8d6459a26eda8a65c1a9d729ff2031cb675295f8449e5421f446e30822984e0b` |
| CMOS5L typical Liberty | `34163f3e7de9f854afac57332ba06f1739b78e7ac35660a8a5ddd39c570124ad` |

The audit receipt also hashes the exact executed driver. `audit.json` adds every
native report, full log, verbatim prefixed resolution stream, native version
stdout and process result. The driver reads an external receipt to avoid an
embedded self-hash cycle, prints it before SDC and completes only after reports.
Launch receipts record actual Docker argv, exit and unchanged pre/post input
hashes. Tool image:
`sha256:d109140b8f17fc54f4fca998beb8124f4949404ec52e339eebd2250854a18b5a`.
Actual tools: Yosys **0.66** / `86f2ddebce7e98ce7cacc27e8a5c14cb53b51b51`,
standalone OpenSTA **2.7.0**. OpenROAD was version-probed only, not a timing producer.

## Executed commands

The full argv, stdout/stderr and result of capture/build/emission are retained
in `capture-01/`, `emitter-build-04/` and `emission-scalar-01/`:

```sh
opam exec --switch=5.2.0+ox -- \
  flock /tmp/opencode/asic-pt7-build.lock \
  python3 -B scripts/asic_dependency.py --store .dev/asic-pt7/provider \
  refresh --source /home/wayne/devel/jane/hardcaml_asic --mode development --jobs 6
# record_command.py supplies the isolated generation's OCAMLPATH/PATH:
python3 -B timing/record_command.py \
  --output acceptance/timing/emitter-build-04 \
  --generation .dev/asic-pt7/provider/current -- \
  opam exec --switch=5.2.0+ox -- \
  flock /tmp/opencode/example-pt7-build.lock \
  dune build --build-dir _build_pt7 -j6 timing/timing_cli.exe
_build_pt7/default/timing/timing_cli.exe emit-scalar \
  /home/wayne/devel/jane/hardcaml_asic_example \
  /home/wayne/devel/jane/hardcaml_asic_example/.dev/asic-pt7/bundle-scalar-01
python3 -B timing/real_tools.py synth --label synth-scalar-01 \
  --bundle .dev/asic-pt7/bundle-scalar-01
python3 -B timing/real_tools.py audit --label sta-scalar-02 \
  --bundle acceptance/timing/synth-scalar-01-bundle \
  --synthesis acceptance/timing/synth-scalar-01
python3 -B timing/check_acceptance.py \
  --generation .dev/asic-pt7/provider/current \
  --audit acceptance/timing/sta-scalar-02 \
  --output acceptance/timing/checked-scalar-02
python3 -B timing/native_negatives.py --attempt 02 --audit sta-scalar-02
```

These are executed commands; a rerun needs **new output names**. Capture's nested
Dune build/install/link-probe ran sequentially at explicit six-job limits.
Synthesis is explicit standalone Yosys mapping of public bundle bytes, not a
claimed named-flow/execution-store run. The exact `synth.ys` is retained. Private
names are enumerated before writing both JSON/Verilog so native queries and the
inventory use the same actual cell names. No cell names are predicted by the
public timing API.

All tool launches ran sequentially with builds under
`/tmp/opencode/example-pt7-sta.lock`: one CPU, 4 GiB, 128 PIDs, no network,
read-only image root and 180-second timeout. Final OpenSTA uses explicit
`-threads 1`; its native help confirms support (`sta-help-01/`). Build workers
never exceeded six. P&R allocation and use were zero.

## Preservation and actual downstream timing

Five original scalar stages survived as distinct `sg13cmos5l_dfrbpq_1` cells.
JSON assertions verify exact Q anchors and unique drivers, all interstage D
connections, primary CLK and actual `rst_n` to RESET_B connectivity:

| Stage | Actual cell | Data source |
| --- | --- | --- |
| capture_first | `_4_` | scalar input `ena` |
| capture_second | `_3_` | capture_first Q |
| capture_third | `_2_` | capture_second Q |
| control_first | `_5_` | `ui_in[1]` |
| control_second | `_6_` | control_first Q |

Native resolution agrees. Capture applies only `ena -> _4_/D`; reset enumerates
all five RESET_B pins. All resolution precedes application. Native capture
min/max samples report `No paths found`. All three downstream links remain timed:

| Native path | Max/setup slack (ns) | Min/hold slack (ns) |
| --- | ---: | ---: |
| `_4_/Q -> _3_/D` | +19.432287 | **−0.044244** |
| `_3_/Q -> _2_/D` | +19.432287 | **−0.044244** |
| `_5_/Q -> _6_/D` | +19.432287 | **−0.044244** |

Assertions check exact native start/endpoints, path types, library setup/hold
text and numeric slack. This proves sampled downstream timing preservation,
**not timing closure**. Hold violations are retained. Analysis is typical-corner,
ideal-clock, zero-interconnect-parasitic synthesized-netlist STA.

## Native diagnostics and B inspection

The native runtime lacks `report_exceptions`; its actual help warning is retained
as `exceptions.rpt`, not converted into passing coverage. `check_setup -verbose`
emitted no diagnostics with actual SDC. Native `report_checks -unconstrained`
bytes are retained; that option can also print constrained paths, so this is not
exhaustive unconstrained coverage.

`native-unconstrained-02` links the same netlist/Liberty **without SDC** as a
separate diagnostic control. Native output retains 19 missing-input-delay ports,
two missing-output-delay ports, five unclocked register pins, seven unconstrained
endpoints and an explicitly unconstrained path. It is not positive audit evidence.

```sh
.dev/asic-pt7/provider/current/bin/hardcaml-asic-flow \
  timing-intent-inspect acceptance/timing/sta-scalar-02 --json
```

Actual invocation/output is retained in `checked-scalar-02/positive/`:
**exit 1**, verdict/native coverage `unavailable`, resolved `producer_reported`,
applied `command_completed`, five stages, two exceptions. Downstream and
unconstrained coverage remain unavailable. The example contains no local timing
parser/resolver; it uses B's public inspection and native-report assertions.

## Negative checks and regressions

Five new native fixtures all exited 1 with the expected diagnostic, **zero
applied records and no complete record**: missing Q anchor; two Q drivers
(ambiguous); buffer driving an anchor (wrong master/role); downstream D reconnected
to external input; capture target changed to second stage in a diagnostic SDC
copy. The first four consumed unchanged emitted SDC. Exact mutations, hashes,
logs and assertions are `negative-*-02*` / `native-negatives-summary-02.json`.
The published bundle was never modified.

Seven B-reader fixtures exited 2: missing resolution, changed SDC hash, wrong
producer, truncated stream, coherent resolved/applied wrong pin scope with
refreshed log hashes, nonzero process despite completion, and wrong native
version. Full bytes/diagnostics are in `checked-scalar-02/`.

`regression-01/command.json` records passing locked `-j6` build of
`bin/project.exe`, `memory/memory_cli.exe`, `@asic_test/runtest`,
`@memory/test/runtest`, `@test/runtest`, `@timing/runtest`: FIFO directed and
20,000-cycle random tests, wrapper gating/ignored inputs, catalog, TT resolution,
and memory Flops/Exact behavior/policy. `emission-regression-01/` records all
**five** existing public named-flow emission compatibility tests passing.

## Failures, skips and unresolved issues

* `emission-01` rejected the owned specimen's unsupported T1x1; corrected to T6x4.
* `emission-02` rejected its missing required pin descriptions; supplied all 24.
  `emission-03` then emitted the bit-source public bundle successfully.
* **A-REAL-1 remains open**: `sta-01` fails the generated bracket-escaped
  `get_ports` lookup for `ui_in[0]`. Five stage anchors resolve, no exception
  applies. Native probe shows raw bit spelling works, generated escaping does
  not. C did not patch library source or emitted SDC. Fix/recapture/re-emission
  belongs to A/B coordination; the captured provider's bit-source subset remains
  unqualified. Full reproducer is in `pt7_timing_findings.md`.
* Scalar attempt `sta-scalar-01` and initial negatives completed with one-CPU
  container/thread environment. Final `*-02` attempts add explicit native
  `-threads 1` after confirming the option. Earlier attempts remain intact.
* Three sampled hold violations remain; no physical repair was allocated.
* No B source bug was observed on the genuine audit. Coordinator independent
  review remains separate. Native coverage is intentionally unavailable.
* No P&R, other-corner closure, analog CDC/MTBF, reset-release protocol, post-PNR,
  or Protemu qualification. No broad Workbench/physical suite was invoked.

Existing dirty files, historical SRAM evidence, old provider selections and app
configuration were not rewritten. Only `asic/project.ml` and
`memory/program_memory.ml` existing Timing literals migrated, preserving I/O
budgets. Closeout observations make no retrospective before/after hash-baseline
claim. `closeout-01/checksums.json` inventories all new PT.7 evidence bytes.
