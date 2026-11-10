# Independent physical timing consumer

## Current ownership-layout entry points

This directory is now `tooling_acceptance/timing/physical`; the shared hardware
is `../fixture/timing_specimen.ml`. From the repository root, with `OCAMLPATH`
pointing at an already installed compatible provider's `lib` directory:

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  opam exec --switch=5.2.0+ox -- dune build --build-dir _build_migration_tooling -j6 \
  tooling_acceptance/timing/physical/physical_timing_cli.exe
_build_migration_tooling/default/tooling_acceptance/timing/physical/physical_timing_cli.exe \
  emit-physical synthesis "$PWD" /tmp/new-physical-timing-bundle
python3 -B tooling_acceptance/timing/physical/acceptance.py --help
```

The commands above build and emit without EDA. The phase harness retains
`_build_timing_physical` but now targets this directory. The following qualification
record preserves historical commands and result identities; use the new directory
prefix for current source entry points. Historical seals still check original
captured bytes and are not assertions that relocated current sources are identical.

## Historical qualification record

This is C's independent public consumer for the bounded physical qualification
plan in `hardcaml_asic/docs/development/timing-physical-qualification.md`.
Actual progress and defects are recorded in
[`../../../docs/timing_physical_findings.md`](../../../docs/timing_physical_findings.md).

`physical_timing_cli emit-physical synthesis|full SOURCE_ROOT NEW_OUTPUT_DIRECTORY`
uses public `Project.elaborate_for_flow` and `Elaboration.Bundle.render
~timing_physical_qualification:true`. It supplies the original five-flop hardware
from `timing/timing_specimen.ml`, with scalar `ena` as the capture source. The
simulation elaboration and immutable bundle are produced through public APIs;
there is no consumer-owned production timing parser or emitted-file patching.

## Isolated preparation

Run from the example checkout. Every attempt name is new; failures remain intact.

```sh
python3 -B physical_timing/preserve.py snapshot \
  --output .dev/asic-timing-physical/original-history.json
python3 -B physical_timing/acceptance.py capture --attempt capture-N
python3 -B physical_timing/acceptance.py build --attempt build-N \
  --generation .dev/asic-timing-physical/provider/generations/EXACT_GENERATION
python3 -B physical_timing/acceptance.py emit --attempt synth-emit-N \
  --generation .dev/asic-timing-physical/provider/generations/EXACT_GENERATION \
  --stage synthesis
```

Private dependency capture uses `--jobs 6` under the shared ASIC lock. Consumer
builds use `_build_timing_physical`, `-j6`, switch5.2.0+ox and the shared example
lock. Commands serialize under C's allocation lock and retain exact argv, thread
environment, elapsed time, process exit status, raw stdout/stderr and hashes.

## Native controls

After the physical API is implemented and a fresh physical SDC is emitted:

```sh
python3 -B physical_timing/native_controls.py --tool sta --case baseline \
  --attempt sta-baseline-N --bundle .dev/asic-timing-physical/bundles/synth-emit-N
python3 -B physical_timing/native_controls.py --tool openroad --case baseline \
  --attempt odb-baseline-N --bundle .dev/asic-timing-physical/bundles/synth-emit-N
```

Additional cases exercise moved anchors, eight/nine-hop bounds, buffered capture,
clock, reset and interstage roles, qualified delay cells, supported stage sizing,
inversion, unknown transforms, root contention and extra architectural state.
The fixture begins with retained mapped Verilog from the old synthesis specimen;
each transformation is a disposable diagnostic fixture only. Every fixture runs in
a separate process with the **unmodified emitted SDC**, read-only PDK/bundle/old
input mounts and a new writable work directory. Docker is pinned to an exact local
image ID with no network, one CPU, one native thread, 4 GiB and 128 PID ceilings.
Timeouts retain failure logs and clean up only the invocation's named container.
Inputs are hashed before/after. Positive controls query the checked native map,
retain five-register inventory and all three interstage min/max paths. Negative
controls must fail before any false-path exception exists or checked map is exposed.

`functional_tb.v` drives away from rising clock edges and checks 512 observations
of the three-stage capture path, two-stage control path, reset and output gating.
It is deterministic functional replay, with no analog/metastability inference.
Its `+negative` mode deliberately fails an observation for checker qualification.

Actual interface controls: `native-suite-01`, `native-fast-01`, `native-slow-01`
passed198 native cases; `native-controls-review.json` rechecks all input/log hashes,
min/max paths and cleanup. `clock_probe.py` qualified the exact propagated-clock
and annotation APIs, including readback of the retained diagnostic ODB.
`check_emission.py` proves the fresh RTL and timing-environment prefix match the
original bytes. `check_testbench.py --rtl-bundle ...` passed512 observations and
an intended negative against emitted RTL; raw-vendor mapped replay exposed the
documented Icarus delayed-signal defect.

## Full acceptance gate

No full run is authorized by preparation success alone. Both A/B runtime/endpoint
handoffs must confirm readiness, native controls must pass and all three synthesis
corners must actually execute. Then use the ordinary public coarse full pipeline
through routing/RCX/STAPostPNR, normal TT and final-netlist postchecks, public
inspection/report/collection/archive, and restored retained-source replay.
Keep completion, native coverage, timing closure and physical/external acceptance
separate. One initial full attempt plus one diagnosed behavior-preserving repair
attempt is the entire current allocation. Preserve all failures and all five
original flops. Further full attempts require coordinator revision.

`public_flow.py` provides `run`, `inspect`, `postcheck` and `public` phases with
exact generation/prepared-input references. Supply the actual B ready handoff to
`run`; full runs also require the actual synthesis inspection. All subprocess
results are retained, including expected coverage-unavailable inspection exits.
`archive_replay.py` restores the public archive and checks inspect/collect/report
parity while original source/PDK paths are hidden by a child mount namespace.
The executed synthesis, full result and portable closeout are recorded below.

## READY6 synthesis checkpoint

The actual fresh baseline is
`.dev/asic-timing-physical/synthesis-runs/20261029T070532999179Z_4821044b`.
`synthesis-baseline-limits-01.json` checks the public all-configured three-corner
view, five original flops, exact native scopes/diagnostics, per-corner libraries,
successful bounded processes and cleanup. Setup/electrical goals pass; hold fails
in every corner and is retained truthfully. `synthesis-public-02` and
`synthesis-restore-01` passed ordinary public evidence/archive/hidden-input replay.

`model_adapter_qualify.py` invokes the captured production `reviewed_timing_cell`
function on actual preflight-pinned vendor sources, then runs actual Icarus against
the fresh mapped input and explicit diagnostic sizing variants. `model-adapter-01`
passed all four reset-flop masters,512 positive observations each, plus four
intentional negatives. It does not invent full-run evidence to bypass normal
postcheck admission. Full launch and final-netlist postchecks remain held for
A's F1–F6 physical provenance corrections at that checkpoint.

## Actual first full result

Coordinator subsequently authorized the corrected fresh generation. Actual run:
`.dev/asic-timing-physical/full-runs/20261029T075052976305Z_23a6954b`.
`full_admission.py` checked both corrected capabilities and unchanged native-
qualified RTL/SDC/producer bytes. Full attempt1 completed routing/RCX/STAPostPNR
and linked all-corner extracted STA; setup/hold/slew/cap/annotation goals pass.
All five architectural flops remain. Ordinary TT precheck and512-observation
final-netlist functional replay pass. Public report exits0. No repair rerun was
needed or launched.

`full_assertions.py` validates actual source hashes, native processes, exact
implementation input State, per-corner goals, five-stage inventory, six exception
relations, thirteen native endpoints (including the added combinational CTS load),
all downstream min/max witnesses, model/netlist association and normal checks.
Result: `full-native-public-acceptance-01.json`.

The first public archive omitted seven original antenna/DRC/LVS reports advertised
by collection. Its failed hidden-input replay remains historical evidence.
`compare_replay.py` records the precise differences without normalizing them away.
See [`../../../docs/timing_physical_full_result.md`](../../../docs/timing_physical_full_result.md)
and the detailed findings. One full attempt consumed; portable closeout below uses
the same retained run, with no new EDA.

## Portable closeout and actual worker accounting

`portable_closeout.py` snapshots pre-correction documentation and all1196 original
run files, then publishes a **new** archive with the separately captured corrected
archiver. Execution remains provider `4856e6af993642988c18c07f47a8c689`; the archiver
is provider `1ba205c2a11c4904b03d98b0e7a3f616`, installed archive source hash
`4c86b6516f31b0c1c18a07364ab85b7c38a9122633debec2cafeac93befb415d`.
No actual run or prior evidence is rewritten.

`full-restore-corrected-01` passes exact original inspect/collect/report parity
with the original run/example/PDK/source hidden, all423 raw artifacts and476
restored files. `portable_verify.py` checks all449 archived member bytes against
the original-run snapshot, all advertised files, both execution/archiver identities
and A's1720-assertion actual review. Final source/receipt package:
`.dev/asic-timing-physical/evidence/portable-package-01/`.

Actual dedicated all-corner pre/post-PNR and linked STA used one thread each.
Mid-PNR OpenROAD36/38/43 requested6 threads; step31 requested1. These all remained
within C's allocation6. The earlier blanket in-flow STA1 description was overbroad;
pre-correction docs are snapshotted, native commands remain unchanged, and the
coordinator explicitly accepted corrected accounting without physical repeat.
The three cell-PVT corners use one nominal extracted RC view. This closeout retains
bounded native coverage and zero-delay functional claims, not exhaustive path-
effect, analog/metastability, vendor delayed-model or silicon certification claims.
