# Program-memory physical run handoff

Layout migration: this historical handoff now lives in
`asics/program_memory/physical/`. Current executable targets and script ownership
are listed in the [specimen README](../README.md#source-ownership-after-the-layout-migration).
The dated commands and immutable evidence paths below retain their original context.

**P4 physical acceptance passed (2026-10-25)**: successful public full run, external
TT/gate postcheck and actual independent collector, with supplemental corrupted-
oracle and portable archive/replay checks. Scope is unchanged stock SRAM/16 staging
flops, extracted physical/electrical checks, abstract macro-boundary LVS with CDL,
and zero-delay gate functionality. Timed SRAM/SDF, internal-device LVS and IR/EM
remain open. C ran offline checks and bounded Icarus/vvp only; the coordinator owns
the actual physical flow. P1/P2/P3 failures below remain immutable failures.
Library/runtime ownership and the exact contract are in
[`sram-example-physical.md`](../../../../hardcaml_asic/docs/development/sram-example-physical.md)
and [`sram-physical-handoff.md`](../../../../hardcaml_asic/docs/development/sram-physical-handoff.md).

## Declaration and placement

Both CLI commands require `--selection flops|exact --operation synthesis|hardening`.
The OCaml declaration accepts optional `~operation:Flow.Operation.Hardening` or
`Synthesis`. Omitting it preserves previous callers: Exact Synthesis, Flops Hardening.
Exact Synthesis retains `(42,81)` R0 and schema 1 / `synthesis_only`. Exact Hardening
declares **`(40,81)` R0**, 2 µm halo, schema 2 / `fresh_full` with generated physical
inputs. `Macro_intent.tt_cmos5l_r0` is unchanged.
Only Exact Hardening drops `RUN_KLAYOUT_DRC`, `FP_PDN_VPITCH`, `FP_PDN_VWIDTH`,
`FP_PDN_MULTILAYER` from the TT template override list. These are now generated
facts. Flops and Exact Synthesis retain all existing template defaults.

The stock macro is 236.8 × 118.78 µm. In the related retained probe, a VPWR M4 stripe
spans x=111.83–113.93 µm and nearby VGND spans 115.93–118.03 µm. The selected positive
macro fingers at x=42 span 113.70–116.51 µm, near/overlapping that ground projection.
Moving to x=40 gives 111.70–114.51 µm: full 2.10 µm VPWR overlap and 1.42 µm separation
from that ground stripe. This is a local positive-rail alignment rationale, **not**
proof that all contacts are legal. Ground access, transformed OBS/signal shapes,
grid trimming, final template application and public pins still need verification.
The provider must derive all bridge coordinates from real geometry and reject a
failed search. Do not reuse the probe's hard-coded bridges or edit an emitted bundle.

The full-width 256×16 latency-one core, two 8-bit staging registers, command decoder,
byte mux and output mask are unchanged. There is no added pipeline/reset synchronizer.

## Timing and electrical acceptance

Keep the specimen assumptions explicit: 48 MHz, 0–1 ns input delays, 0–2 ns output
delays, 0.25 ns uncertainty, 0.15 ns clock transition, 0.95/1.05 derates, fanout 10,
`sg13cmos5l_buf_4/X` input/clock driving cells, 0.006 pF output loads. Inherited output
port repair buffering is disabled. Do not reduce load, idealize drivers, relax SRAM
Liberty limits, insert registers, or omit corners to make acceptance pass.

The separate direct-pad probe had 25 slow-corner slew and 12 capacitance violations
despite positive setup/hold slack. Example values were 1.252720 ns at `A_ADDR[1]`
against 0.595200 ns, and 0.104796 pF at `A_DOUT[13]` against 0.064000 pF. These are
diagnostic precedent, not measured failures of this consumer. Preserve/report actual
violating pins, loads, corners, paths and raw metrics from this consumer's run.
Combinational buffering, sizing and placement can be evaluated without changing
latency. Preserve the fast standard-cell −40°C / SRAM −55°C discrepancy explicitly.

## Installed-provider validation (2026-10-25)

Six-job development refresh/install and external API/link probes passed. Installed
generation (absolute):

```text
/home/wayne/devel/jane/hardcaml_asic_example/.dev/asic-sram/generations/dd1ac48f0f5c4f03ae4580edb722ce47
```

Receipt observed base: `ca4a42e30c11aff66cd1679d13e7175cce59a9b0`.
Captured source SHA-256:
`666530db0dc67f56e174154b570fb5c9136c8b0b9d224d739243456717a4cc71`.
Captured bytes differ from that base and the historical dependency pin. This is a
local development receipt, not a clean/released source claim.

The following completed against this generation, without transitional expectations:

```sh
. "$PWD/.dev/asic-sram/current/activate.sh"
dune build --build-dir _build_sram -j6 memory/memory_cli.exe memory/test/memory_test.exe
dune runtest --build-dir _build_sram -j6 memory --force
python3 -B memory/check_bundle.py \
  --cli "$PWD/_build_sram/default/memory/memory_cli.exe" \
  --core-exporter "$PWD/_build_sram/default/memory/test/memory_test.exe" \
  --source-root "$PWD" --pdk-root "$PWD/_flow_tools/pdk" \
  --require-rtl
```

Results: **5,376** core-test edges; all four selection/operation combinations passed
deterministic emission, complete hashes/source provenance and nonempty-output
refusal. Eight TT replays passed **10,240 word checks**; two direct Exact vendor-core
replays passed **3,072 response checks / 4,096 edges**. All ten corrupted-data oracles
rejected. Both selections have byte-identical implementation and simulation RTL
between operations. Core RTL has no local registers; Exact TT RTL retains only the
two original staging bytes. Hardening without complete intent rejects.

Schema-2 assertions cover the complete embedded/file plan, both supply hooks,
Metal1 rails/trim/ring/halos, native Metal4 grid, Metal4-only footprint obstruction,
KLayout real-GDS profile/options/six-worker settings and schematic CDL declaration.
These are source/bundle checks, not actual power/DRC/LVS/worker execution evidence.

## After final A/B handoff: example validation and emission

The A/B handoff capture and complete matrix are now validated. For a future capture,
use the six-job isolated refresh in [README.md](../README.md#isolated-dependency-and-validation),
record the new receipt, rebuild/retest with `_build_sram -j6`, and rerun the full
matrix without `--expect-hardening-unsupported`. The historical pin remains unchanged.

The following fresh immutable P1 bundle was emitted successfully after the complete
matrix passed:

```text
Directory: /home/wayne/devel/jane/hardcaml_asic_example/.dev/program-memory-exact-physical-p1
Identity:  29c260aaea84eb5d94fce9a12871ddee9eec8897f486c6cfa4b6497f44d2d8f2
```

It contains the matching generated plan/PDN Tcl and the unchanged clock, driver,
load and I/O-delay SDC. Its preserved source inputs include the exact dirty/untracked
example bytes; no clean-checkout claim is made. This handoff record is outside the
bundle's declared source inputs. Historical C1/C2 checksum inventories still pass.

Emission command used (P1 now exists; select a new directory on any repeat):

```sh
MEMORY="$PWD/_build_sram/default/memory/memory_cli.exe"
BUNDLE="$PWD/.dev/program-memory-exact-physical-p1"
"$MEMORY" check --selection exact --operation hardening
"$MEMORY" emit --selection exact --operation hardening \
  --source-root "$PWD" --output-dir "$BUNDLE"
```

## Coordinator-only EDA and postchecks

### P1 failure → bounded PDN diagnostic → P2 refresh (2026-10-25)

The coordinator's immutable P1 run at
`_flow_results/sram-physical/runs/20261025T010527676274Z_9c439718`
failed during native PDN generation with **PDN-0232/PDN-0233**. The empty default
native macro grid had no shapes/vias for the same-Metal4 strategy, so edge-access
construction was never reached. P1 and its original provider generation remain
preserved. Its earlier successful bundle/RTL checks did not establish PDN success.

A corrected generated Tcl to define only the native standard-cell grid and supply
the macro through checked edge access afterward. **No schema/configuration change**:
`PDN_CONNECT_MACROS_TO_GRID=true` and both supply hooks remain intact. The exact
details and independently checked artifacts are in the provider handoff's
“Native PDN correction” section.

A's six-worker real OpenROAD diagnostic in `/tmp/opencode/sram-pdn-native-fix-03`
passed both VPWR and VGND grid checks, with `VDD!` and `VDDARRAY!` on VPWR and
`VSS!` on VGND, one stock SRAM and the original 16 staging flip-flops. Its
`verification.json` records both connected grids, six saved bridge rectangles and
two public pins; the grid error reports contain no violations. This is bounded
**PDN-stage construction/connectivity evidence**, not completed full-flow,
routed DRC/LVS/electrical acceptance. C read the retained diagnostic result; C did
not launch OpenROAD or repeat the diagnostic.

New six-job isolated capture, install and API/link probes passed:

```text
Generation: /home/wayne/devel/jane/hardcaml_asic_example/.dev/asic-sram/generations/5ce7fdbb5a1443b89943d35946eb168d
Observed base: ca4a42e30c11aff66cd1679d13e7175cce59a9b0
Development snapshot SHA-256: 4faf4fe48e51c07023d75986ba61acb2dc531117241bb33b5e4d1227da128fa0
Bundle: /home/wayne/devel/jane/hardcaml_asic_example/.dev/program-memory-exact-physical-p2
Bundle identity: 0919a6c6b801d69dfa736a3f8068d3197d77330c01bd75a8b7cdbf7efa2e0bb9
```

The captured development bytes differ from the observed base; the historical pin
is unchanged. `_build_sram -j6` focused build and memory tests passed (5,376 core
edges), followed by a focused Exact Hardening deterministic/hash/provenance audit:

```sh
. "$PWD/.dev/asic-sram/current/activate.sh"
python3 -B memory/check_bundle.py \
  --cli "$PWD/_build_sram/default/memory/memory_cli.exe" \
  --core-exporter "$PWD/_build_sram/default/memory/test/memory_test.exe" \
  --source-root "$PWD" --pdk-root "$PWD/_flow_tools/pdk" \
  --operations hardening --selections exact --skip-rtl \
  --compare-bundle "$PWD/.dev/program-memory-exact-physical-p1"
```

Two fresh emissions were byte-identical, complete file/source hashes passed,
schema-2 settings passed, and nonempty-output refusal preserved bytes. Comparison
against hash-verified P1 proved unchanged contract, configuration, plan, SDC and
implementation/simulation RTL, while generated Tcl and bundle identity changed.
Structural checks still require exactly the original two byte registers. The full
RTL replay matrix was deliberately not repeated: P1 already passed it and the
focused refresh proved identical hardware bytes.

| Input | P1 SHA-256 | P2 SHA-256 |
| --- | --- | --- |
| `physical/macro-plan.json` | `1bd46cebcd09aad77f29ae3bb21212ca04b6bd17be5f3dc67753481db1561748` | `1bd46cebcd09aad77f29ae3bb21212ca04b6bd17be5f3dc67753481db1561748` |
| `physical/pdn.tcl` | `8b612d6858d7c71e9e43aec88b11bf65e3677c1dabfde42c5ad408556d94492c` | `a1795098f315d1720aed470efabb7f3fc930a97c0a0bc02cbf4e984e4ebcaf9e` |

The unchanged plan hash is expected: only Tcl generation changed. P2's Tcl hash
matches A's successful bounded diagnostic exactly. P2 was emitted to a fresh
directory after the focused checks; P1 was not edited. The P2 full run remains
coordinator-owned and unrun at this handoff.

### P2 LVS/slew failure → runtime/electrical corrections → P3 (2026-10-25)

The subsequent P2 run `79df6b00` remains failed: LVS **35**, extracted slew
violations **1 fast / 2 slow / 1 typical**, capacitance **0** in all corners,
and real-GDS KLayout **0**. It is not relabeled accepted. See the provider handoff
for the retained run and bounded diagnostic artifacts.

B's actual isolated Netgen adapter diagnostic passes abstract macro-boundary LVS
with one SRAM on each side and all 109 pins matched; swapped-address and
VDDARRAY-to-ground negative controls fail. The packaged `macro_flow.py` uses
hash-recorded naming-only reader views and retains supplied CDL/netlist inputs.
Its target-specific policy audit retains the original failed metrics and checks
real GDS, power and narrowly classified Magic diagnostics. This is bounded proof,
not a fresh full-flow result.

A's native post-GRT repair diagnostic inserts **99 non-inverting buffers**, no
registers, and clears estimated all-corner slew/cap with positive estimated
setup/hold. P3 adopts the generated physical-only settings:
`RUN_POST_GRT_DESIGN_REPAIR=true`, `GRT_DESIGN_REPAIR_RUN_GRT=true`,
`GRT_DESIGN_REPAIR_MAX_WIRE_LENGTH=200.0` µm, slew/cap repair margins **20%**, and
`RSZ_CORNERS` equal to the exact fast/slow/typ STA corner list. Margins are repair
guardbands, not relaxed Liberty or SDC limits. Actual detailed-route extracted
electrical checks, DRC/LVS and replay must still pass the coordinator's new run.

C captured/installed the integrated provider with six jobs, rebuilt `_build_sram
-j6` and passed focused memory tests (5,376 edges). Exact identities:

```text
Generation: /home/wayne/devel/jane/hardcaml_asic_example/.dev/asic-sram/generations/bd7bf3ff861a48a5bf3df6a50b2a1f93
Observed base: ca4a42e30c11aff66cd1679d13e7175cce59a9b0
Development snapshot SHA-256: c05e45cbba531d63c6b2edc2f3994dc8b246f07ac086ec1b2a0191722b5c8003
Bundle: /home/wayne/devel/jane/hardcaml_asic_example/.dev/program-memory-exact-physical-p3
Bundle identity: fa38d9064dffdf2ec1578c79c2e8890eba81bf704af460e85fcc6031b707d53c
```

The four-way **bundle-only** matrix passed deterministic emission, provenance,
hashes, operation-specific canonical settings and structural register checks.
Physical repair settings are absent from all nonphysical paths. Focused comparison:

```sh
python3 -B memory/check_bundle.py \
  --cli "$PWD/_build_sram/default/memory/memory_cli.exe" \
  --core-exporter "$PWD/_build_sram/default/memory/test/memory_test.exe" \
  --source-root "$PWD" --pdk-root "$PWD/_flow_tools/pdk" \
  --operations hardening --selections exact --skip-rtl \
  --compare-bundle "$PWD/.dev/program-memory-exact-physical-p2" \
  --compare-profile electrical
```

This passed with **exactly six expected configuration changes** and no others.
Contract, plan, PDN Tcl, implementation/simulation RTL and SDC are byte-identical
to hash-verified P2. Plan/Tcl SHA-256 remain respectively
`1bd46cebcd09aad77f29ae3bb21212ca04b6bd17be5f3dc67753481db1561748` /
`a1795098f315d1720aed470efabb7f3fc930a97c0a0bc02cbf4e984e4ebcaf9e`.
The unchanged full HDL replay matrix was not repeated.

The installed generation includes `flow/hardcaml_asic_flow/macro_flow.py` and
`physical_runtime.py`. Using `_flow_tools/.venv/bin/python -B` with this immutable
generation's `lib/hardcaml_asic/flow` on `PYTHONPATH`, imports passed and
`macro_flow.install(P3, helper=physical_runtime.__file__)` installed exactly one
`Netgen.LVS` adapter in Classic. The same process ran LibreLane `--help` and exited
successfully without `Flow.start`. These are installed-package/import/CLI checks,
not Netgen or physical execution. P3 was emitted fresh; P1/P2 and their providers
are preserved. No C EDA, provisioning, pin change or Git mutation was performed.

### P3 native completion / public policy failure → P4 (2026-10-25)

P3 run `20261025T023413976323Z_cf909599` reached native flow completion with actual
electrical/DRC/LVS metrics zero, but its public run record remains **failed** for
unclassified stock-LEF M2 markers. B's updated policy passed the complete physical
checker on a disposable clone, with all 50 artifact hashes verified and unchanged
real GDS/netlist/metrics. Four same-routed-DEF controls reproduce stock findings,
remove only each targeted wide M2/M3 obstruction's findings, and clear the combined
control. This is narrow counterfactual evidence, not a blanket Magic waiver or a
successful relabeling of the original P3 run. External TT/gate postchecks remain
pending.

C captured/installed the updated provider with `--jobs 6` and rebuilt the focused
example targets using `_build_sram -j6`:

```text
Generation: /home/wayne/devel/jane/hardcaml_asic_example/.dev/asic-sram/generations/71a9a125992e4260b38dcdf954c6b965
Development snapshot SHA-256: 632cb3358e36d193d3a580b9fa11164b8f376673d259bfbcfdd46ee1fdf68b99
Observed base: ca4a42e30c11aff66cd1679d13e7175cce59a9b0
Bundle: /home/wayne/devel/jane/hardcaml_asic_example/.dev/program-memory-exact-physical-p4
Bundle identity: fa38d9064dffdf2ec1578c79c2e8890eba81bf704af460e85fcc6031b707d53c
```

Focused deterministic emission/hash/provenance/refusal checks passed using
`--operations hardening --selections exact --skip-rtl --compare-bundle
"$PWD/.dev/program-memory-exact-physical-p3" --compare-profile runtime`.
**Every P4 bundle byte and its identity equal P3**: the policy lives in the captured
runtime, not emitted hardware/configuration. No full RTL matrix was repeated.
Installed updated runtime/adapter imports, Classic Netgen installation and CLI help
passed without starting a flow. P1/P2/P3 bundles, generations and evidence remain
preserved. The final public full run/postcheck is coordinator-owned and unrun by C.

The coordinator owns actual EDA allocation. No provision step or physical tool is
launched by example check/emission. After validation, the public coarse endpoint is
`full`, not `hardening`. Confirm effective six-worker limits and serialized STA
from the final provider before launch. No segmented/checkpoint route is implied.

```sh
GENERATION="$PWD/.dev/asic-sram/generations/71a9a125992e4260b38dcdf954c6b965"
PROVIDER="$GENERATION/bin/hardcaml-asic-flow"
BUNDLE="$PWD/.dev/program-memory-exact-physical-p4"
"$PROVIDER" preflight "$BUNDLE" --toolchain "$PWD/_flow_tools" \
  --results-root "$PWD/_flow_results/sram-physical" --json
"$PROVIDER" run "$BUNDLE" --toolchain "$PWD/_flow_tools" \
  --results-root "$PWD/_flow_results/sram-physical" --stage full --json
# Set RUN to the exact run directory returned above, including for a failed run.
"$PROVIDER" postcheck "$RUN" --toolchain "$PWD/_flow_tools" \
  --testbench "$PWD/memory/replay.v" --testbench-top memory_replay --timeout 1800 --json
"$PROVIDER" collect "$RUN" --stdout --json
"$PROVIDER" report "$RUN" --json
```

Preserve failures and raw diagnostics. Postcheck retains actual final-netlist
functional replay, checked zero-delay standard-cell derivation and stock SRAM models.
Public postcheck does not run a corrupted-data oracle; C subsequently ran it against
the original public compiled gate read-only, and against the portable snapshot.
FUNCTIONAL replay establishes neither SDF nor timed conformance.

## Independent evidence preparation

`check_physical.py` now provides an **offline public-record acceptance audit and
evidence collector**. It requires an actual successful public full-run record and
completed external TT/gate postchecks; native exit 0 or a passing diagnostic clone
alone cannot pass. It launches no EDA, checker diagnostics, simulations or subprocesses.
Run it with the existing LibreLane Python environment for raw Magic report parsing.

It verifies complete bundle/staged hashes, canonical settings, one SRAM/16 staging
flops, public/flow `physical-checks.json` identity, run/installed checker and driver
hashes, every physical artifact, final/checked GDS binding, zero KLayout XML/JSON,
all-corner electrical counts/slacks, supplied CDL/actual Netgen reader validation,
power report and final public-LEF binding. It reclassifies retained raw Magic reports
with the hash-bound installed **pure** policy functions and verifies exact diagnostic
LEF derivation/control hashes; it never invokes the tool-running checker functions.

External postchecks must match the run/bundle/GDS/netlist/testbench, both checks must
pass, process receipts must show successful exits within the recorded worker budget,
and logs/reports must exist. Original/derived model hashes, preflight-bound sources
and exact reviewed final-used-cell zero-delay derivation are verified. Acceptance
scope remains **abstract macro-boundary LVS with schematic CDL** and **zero-delay
gate functionality**, not internal-device LVS, IR/EM or timed SRAM/SDF conformance.
The collector itself launches no replay; supplemental receipts below establish the
new corrupted-oracle checks separately.

Optional capture requires a new directory, retains raw provenance, final GDS,
physical reports/controls, external postcheck receipts/logs/reports/models and bundle
inputs, and creates a complete SHA-256 inventory compatible with
`acceptance/sram/verify.py`. A passing audit reports `physical_acceptance: true` only
within the explicitly recorded scope. Missing/failed/stale evidence rejects rather
than producing a preliminary passing result. Actual P4 audit/capture passed as
recorded in the closeout below.

```sh
"$PWD/_flow_tools/.venv/bin/python" -B memory/check_physical.py \
  --bundle "$BUNDLE" --run-root "$RUN" --provider-generation "$GENERATION"
# Capture used after successful full flow AND external postcheck (P4 now exists;
# choose a NEW directory on a repeat):
"$PWD/_flow_tools/.venv/bin/python" -B memory/check_physical.py \
  --bundle "$BUNDLE" --run-root "$RUN" --provider-generation "$GENERATION" \
  --evidence-dir "$PWD/acceptance/sram/physical-p4"
python3 acceptance/sram/verify.py acceptance/sram/physical-p4
```

Focused verification: `python3 -B memory/test/physical_records_test.py -v` passed
**10** offline tests covering exact controls and missing/shifted/unknown findings,
hash/path tampering, wrong run, missing gate checks, timeout/budget violations,
changed final netlist, resealed model inversion and malformed metrics. A separate
read-only check parsed B's retained clone and verified all **50** artifact hashes
and its four-control disposition. The original failed P3 public record was explicitly
rejected by the collector despite that passing clone. These are fixture/offline
checks, not new physical or external-postcheck execution.

Retain exact successful and failed run identities in new evidence directories. Do
not modify historical `cfd39c58/`, `cfd39c58-functional/` or `8b48d7d0-functional/`.

## Actual P4 acceptance and portable-evidence closeout (2026-10-25)

Public full run **`be961b2c95f74c81ad6af81ca4d2b269`**:

```text
/home/wayne/devel/jane/hardcaml_asic_example/_flow_results/sram-physical/runs/20261025T034710180883Z_be961b2c
```

Public record is completed/full, native exit 0. External postcheck
**`0553f6d19c8f42d28c057fc65ed23510`** is completed with TT precheck and gate-level
replay both pass. Collection has no errors, every physical/electrical check passes,
and reported worst setup/hold slack is **11.246561 / 0.223533 ns**. The actual
independent collector command above passed against generation `71a9a125...` and
immutable bundle P4, capturing `acceptance/sram/physical-p4/`.

One collector assumption was corrected from the actual final netlist: `dlygate*`
are combinational hold-delay cells, not `dl*` latch storage. The storage inventory
excludes precisely that delay-cell family and still rejects other added storage.
The real netlist has one unchanged stock SRAM and exactly **16 staging flip-flops**;
23 standard-cell types include physical buffering/delay and filler/decap cells.
Raw final instance count **68,929** includes fillers/decaps; the physical metrics
report **389 standard cells + 1 macro** excluding those physical-only cells.

| Corner | Setup slack ns | Hold slack ns | Setup/hold/slew/cap/fanout violations |
| --- | ---: | ---: | --- |
| Fast | 15.809827 | 0.223533 | all 0 |
| Slow | 11.246561 | 0.814843 | all 0 |
| Typical | 14.150889 | 0.430151 | all 0 |

Routing/KLayout real-GDS DRC, illegal overlaps, abstract-boundary LVS, power-grid,
antenna and critical-disconnected-pin counts are zero. All three macro supply
contacts and final public pins pass the recorded physical policy. **Raw Magic
count stays 3**, dispositioned 3, unclassified 0, with the exact stock/per-layer/
combined controls retained. Stock SRAM implementation collateral is unchanged;
the derived diagnostic LEFs are never implementation or LVS inputs.

### Replay controls and original-artifact integrity

`memory/complete_physical.py` ran the original public **Icarus 13** `gate.out`
with `+negative` in its already-local recorded image, `--cpus=4 --read-only`, a
read-only original-run mount and no network. It exited **1** on the intended first
low-byte mismatch (`addr=19 expected=b62e got=2f`). Only fresh evidence logs were
written. No original netlist/model/testbench/executable was changed.

A standard-library tar restore of the captured evidence was then compiled with
host **Icarus 12** using only retained final-netlist/testbench/model files. Positive
replay passed **1,280 word checks**, corrupted oracle exited **1**. The finalized
delivered archive was separately restored, checksum-verified and compiled/replayed
again successfully. Snapshot and replay-input hashes match before/after. Original
run/PDK/bundle/gate hashes and added public-record source hashes also match before/
after; receipts are in `supplemental/` and the archive-check proof directory.

No full RTL matrix, synthesis, place/route, DRC/LVS or TT precheck was re-executed
by C during this closeout. New subprocesses were limited to four CPUs. This replay
is zero-delay functionality: timed SRAM model/SDF conformance remains untested.

### Retained deliverables and commands

- `acceptance/sram/physical-p4/`: **237 files / 85,863,331 bytes**, complete SHA-256
  inventory verified; includes public run/results, all physical policy artifacts,
  final GDS/netlist/metrics, external TT/gate reports/models, supplemental controls
  and compact failed-attempt chronology.
- `acceptance/sram/physical-p4.tar.gz`: **8,789,090 bytes**, SHA-256
  `91503ecea09bd81fbe880874e4bd18737b1d5030ac206e3176656dd65f2aeb52`.
- `acceptance/sram/physical-p4-archive-check/`: **12 files / 9,014 bytes**, verified
  final-archive restoration plus portable positive/negative replay logs and receipt.
- `failed-attempts/p1`, `p2`, `p3` retain original failed status/errors, exact bundles,
  generation receipts, raw selected logs/reports and metrics (about 4 MB total).
  Large previous GDS/netlist outputs are hashed instead of duplicated. C1/C2
  snapshot verification still passes and no checksum-covered historical files changed.

Practical read-only verification and portable replay (new output directory):

```sh
python3 acceptance/sram/verify.py acceptance/sram/physical-p4
python3 acceptance/sram/verify.py acceptance/sram/physical-p4-archive-check
python3 memory/replay_snapshot.py --snapshot "$PWD/acceptance/sram/physical-p4" \
  --output-dir /tmp/opencode/sram-p4-replay-NEW
```

For another machine, extract `physical-p4.tar.gz`; inside `physical-p4/`, run
`python3 verify.py .` and its `replay_snapshot.py` with a fresh external output.
These need only standard-library Python plus installed Icarus for replay, not the
original PDK/provider/workspace. Raw absolute paths remain provenance. Re-executing
physical tools or the original external-input audit still needs the recorded
dependencies. Accepted scope excludes internal-device LVS, IR/EM adequacy and
timed SRAM/SDF; the fast standard-cell −40°C / macro −55°C difference remains explicit.

This closeout documentation postdates P4's preserved source copies. No new bundle,
provider capture, pin change or Git mutation was performed.
