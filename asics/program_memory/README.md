# Registered program-memory SRAM testbed

## Source ownership after the layout migration

This specimen lives at `asics/program_memory/`. The combined core, TT adapter,
and project declaration remain in `project/program_memory.ml`; the CLI and its
Dune library are also in `project/`. Core/wrapper tests, replay benches,
`check_bundle.py`, `check_mapped.py`, and `replay_snapshot.py` live in `verif/`.
Physical capture/package/check harnesses and their shared contracts live in
`physical/`. The conventional executable targets are:

```sh
dune build --build-dir _build_migration_hw -j6 \
  asics/program_memory/project/memory_cli.exe \
  asics/program_memory/verif/memory_test.exe
```

The dated acceptance narrative below preserves historical commands and provider
identities. For current commands, translate `memory/memory_cli.exe` to
`asics/program_memory/project/memory_cli.exe`, `memory/test/memory_test.exe` to
`asics/program_memory/verif/memory_test.exe`, and the verification/physical scripts
according to the ownership above. Retained `acceptance/` snapshots are unchanged.

## PT4 preparation and live inventory

`memory_cli prepare` invokes public `Preparation_service.run_cli`, constructing
the project inside the allocated closure and passing `on_phase` to
`Project.prepare_resources`. `preview` computes the same implementation evidence
without publication; `resources` returns a nonpublishing inventory (default
Implementation, explicit `--simulation` for behavioral elaboration).
See [commands and acceptance](../../docs/resource_preparation.md).

Selection now also accepts `fallback` (`Exact_or_flop_fallback`); the explicit
`--depth 128` fixture has no exact stock macro, exercising real flop fallback or
an Exact rejection without rounding. Default depth remains 256 and the accepted
SRAM declarations/evidence retain their existing operation/intent behavior.

Independent of the FIFO, this is a real public `Single_port_ram.create` consumer:
**256 words × 16 bits, one shared read/write port, read latency one**, stable
resource ID **`program`**. `program_memory.ml` contains the typed full-width core,
a small byte-wide TT adapter, and the project declaration. It uses production
`Technology.ihp_sg13cmos5l`, never an experimental mapping or local macro RTL.

This is the ongoing production-style SRAM consumer. Exact now selects stock
`RM_IHPSG13_1P_256x16_c2_bm_bist` through the production backend, retaining the
original cycle contract and **no new architecture registers**. The existing two
8-bit TT staging registers remain consumer-owned. The CLI requires independent
`--selection flops|exact` and `--operation synthesis|hardening` arguments for both
`check` and `emit`. OCaml `Program_memory.project ?operation` retains its old defaults
when omitted: Exact Synthesis, Flops Hardening.

The Exact declaration includes optional consumer intent using
`Macro_intent.tt_cmos5l_r0 ~resource:(Resource.Id.of_string_exn "program")
~x_um:42. ~y_um:81. ~halo_um:2. ()` for Synthesis, passed with `Flow.librelane ~macros`.
Explicit Hardening instead declares the candidate **`(40,81)` R0**, same 2 µm halo.
`Program_memory.project ~with_macro_intent:false Exact` explicitly omits that intent;
the CLI uses the declared intent. The actual emitted instance is
**`hc_resource_7_program`**. R0, halo and power mappings are declarative intent;
actual P4 power/physical evidence is identified below. The captured provider supports
Exact Hardening with schema 2 / `fresh_full` and generated
`physical/macro-plan.json` / `physical/pdn.tcl`, strategy
`cmos5l_m4_edge_access_v1`; schema-1 synthesis remains available. On the physical
macro path only, `Tt_cmos5l.overrides ~without` removes `RUN_KLAYOUT_DRC`,
`FP_PDN_VPITCH`, `FP_PDN_VWIDTH` and `FP_PDN_MULTILAYER`: the provider generates
these facts. All other selection/operation paths retain their template defaults.
The declaration alone is not physical evidence; P4 below is the accepted run.

**Initial physical-capable development capture (P1, historical):**
`.dev/asic-sram/generations/dd1ac48f0f5c4f03ae4580edb722ce47`, observed base
`ca4a42e30c11aff66cd1679d13e7175cce59a9b0`, captured SHA-256
`666530db0dc67f56e174154b570fb5c9136c8b0b9d224d739243456717a4cc71`.
This differs from the observed base and historical recorded pin; it is not a
released pin or a clean-checkout claim. Six-job refresh/install/probes, `_build_sram
-j6` build, memory tests (**5,376 edges**) and the full four-way bundle/RTL matrix
passed. Eight TT replays passed **10,240 word checks**, two direct vendor-core
replays passed **3,072 response checks / 4,096 edges**, and all **ten** corrupted
oracles rejected. Both selections have byte-identical implementation/simulation RTL
across operations. Exact Hardening without complete intent is rejected.

## Accepted P4 physical checkpoint (2026-10-25)

Public full run **`be961b2c95f74c81ad6af81ca4d2b269`** and external postcheck
**`0553f6d19c8f42d28c057fc65ed23510`** passed; public collection/report have passing
checks and no errors. The independent collector passed against the actual run.

- Bundle `.dev/program-memory-exact-physical-p4`, identity
  `fa38d9064dffdf2ec1578c79c2e8890eba81bf704af460e85fcc6031b707d53c`.
- Provider `.dev/asic-sram/generations/71a9a125992e4260b38dcdf954c6b965`, captured
  SHA-256 `632cb3358e36d193d3a580b9fa11164b8f376673d259bfbcfdd46ee1fdf68b99`.
  This development receipt differs from its observed base; the historical pin is unchanged.
- One unchanged stock SRAM, latency one, exactly **16 original staging flip-flops**;
  no new architectural registers. Combinational delay/buffer cells are not storage.
- Worst extracted setup slack **11.246561 ns**, hold **0.223533 ns**. Setup/hold/
  slew/cap/fanout violations are **0 at all three corners**. Routing/KLayout DRC,
  illegal overlaps, abstract-boundary LVS, power-grid and antenna violations are zero.
- Raw Magic count **3**, exact four-control stock wide-LEF-obstruction disposition
  **3**, unclassified **0**; diagnostic-only LEFs never replace stock implementation
  collateral. LVS scope is **abstract macro boundary with schematic CDL**, not devices.
- External TT precheck and final-gate replay pass. Portable replay passes **1,280
  word checks**; both the original compiled gate and portable replay reject the
  corrupted expected low byte. Functional scope is **zero-delay**, not timed SRAM/SDF.

Durable evidence: [`acceptance/sram/physical-p4/`](../../acceptance/sram/physical-p4/),
**237 files / 85,863,331 bytes** verified. The **8,789,090-byte** portable archive
was restored, checksum-verified and replayed using only retained sources/models.
Compact P1/P2/P3 failures remain failed and are retained with raw records/logs,
exact bundles and hashes. C1/C2 synthesis snapshots are unchanged.

```sh
python3 acceptance/sram/verify.py acceptance/sram/physical-p4
python3 memory/replay_snapshot.py --snapshot "$PWD/acceptance/sram/physical-p4" \
  --output-dir /tmp/opencode/sram-p4-replay-NEW
```

Timed SRAM conformance, internal-device LVS and IR/EM adequacy remain open. The
fast standard-cell −40°C / macro −55°C model difference remains explicit. Source
docs updated for this closeout postdate P4's immutable input copies; use those
copies and its captured receipt for exact attribution. See [PHYSICAL.md](physical/PHYSICAL.md).

**Current accepted synthesis checkpoint:** C2 run
`8b48d7d0818d494f8a9c45000c2bcbbd`, using corrected-validator generation
`.dev/asic-sram/generations/aa00a92d707447fcba308789e57fa2f6`.
Its actual mapped gate replay passed; see the final C2 section below. Earlier C1
evidence remains historical and unchanged.

## Isolated dependency and validation

The PT.0 historical private generation was
`.dev/asic/generations/3c70c76700764a58974ef7d969adba36`, observed provider base
`ad290d825272b588eb0fe0202e84ce407ae221f5`, captured snapshot SHA-256
`4d804d7f454a940bd93a9a5b72192922c901011e2f0d18e3413ac5c095f78f3f`.
The adoption capture is instead stored in **`.dev/asic-sram`**, keeping FIFO and
Workbench selections independent. The old `asic-dependency.json` pin remains unchanged.
Refresh explicitly captures current provider worktree bytes without Git writes.
The A/B handoff capture above is installed and validated. The following sequence
documents refresh/rebuild for a later intentional capture; source the existing
immutable generation directly when no refresh is needed:

```sh
python3 scripts/asic_dependency.py --store "$PWD/.dev/asic-sram" refresh \
  --source /home/wayne/devel/jane/hardcaml_asic --mode development --jobs 6
. "$PWD/.dev/asic-sram/current/activate.sh"
python3 scripts/asic_dependency.py --store "$PWD/.dev/asic-sram" status --json
ocamlfind query hardcaml_asic
dune build --build-dir _build_sram -j6 memory/memory_cli.exe memory/test/memory_test.exe
dune runtest --build-dir _build_sram -j6 memory --force
MEMORY="$PWD/_build_sram/default/memory/memory_cli.exe"
"$MEMORY" check --selection flops --operation synthesis
"$MEMORY" check --selection exact --operation synthesis
python3 memory/check_bundle.py --cli "$MEMORY" \
  --core-exporter "$PWD/_build_sram/default/memory/test/memory_test.exe" \
  --source-root "$PWD" --pdk-root "$PWD/_flow_tools/pdk" --require-rtl
```

The default matrix requires both selections and both operations to pass, including
functional RTL and corrupted-oracle replays. `--operations synthesis` is a focused
schema-1 regression run. The historical `--expect-hardening-unsupported` flag is only
for the older pre-physical provider, not the current capture. No mode launches EDA.

Every CLI invocation requires explicit selection and operation. There is no fallback:
the policy has only an instance rule for `program` and no default. `check`
elaborates/resolves without reading source or creating output; `emit` uses public
`Project.emit_bundle` with both implementation and simulation RTL and explicit
source provenance. Output must be new/empty. No command invokes physical tools.
The 48 MHz clock and 0–1 ns input / 0–2 ns output delays remain specimen assumptions.
P4 establishes the Exact consumer's extracted timing under those assumptions,
not fit/timing of a 4096-flop replacement in TT6x4.

Exact selection succeeds in both elaboration modes. Simulation remains a generated
behavioral model; Implementation directly instantiates the selected stock macro.
Unsupported 128×16 Exact requests still fail in both modes without fallback or rounding.

## Coordinator-only public synthesis launch

After validation, emit a fresh immutable bundle (choose a new directory on repeats):

```sh
. "$PWD/.dev/asic-sram/current/activate.sh"
MEMORY="$PWD/_build_sram/default/memory/memory_cli.exe"
PROVIDER="$PWD/.dev/asic-sram/current/bin/hardcaml-asic-flow"
BUNDLE="$PWD/.dev/program-memory-exact-next"
"$MEMORY" emit --selection exact --operation synthesis --source-root "$PWD" --output-dir "$BUNDLE"

# Coordinator runs these separately when allocated; neither ran for assignment C.
"$PROVIDER" preflight "$BUNDLE" --toolchain "$PWD/_flow_tools" \
  --results-root "$PWD/_flow_results/sram" --json
"$PROVIDER" run "$BUNDLE" --toolchain "$PWD/_flow_tools" \
  --results-root "$PWD/_flow_results/sram" --stage synthesis --json
```

This is the installed provider's **fresh coarse synthesis** route, not a custom
executor or FIFO/named-stage dispatch. The provider caps this macro route at six
LibreLane/OpenROAD/KLayout/OMP cores and one STA corner worker. Schema-1 bundles
remain synthesis-only; schema-2 Hardening uses fresh coarse full execution as
documented in [PHYSICAL.md](physical/PHYSICAL.md). Macro segmented stages/checkpoints remain
unsupported. Keep all Dune
commands at `-j6` or lower. Emission/functional acceptance do not run EDA or preflight.

The manifest's `macro_contract` binds logical resource to actual instance, stock
collateral, explicit physical intent and synthesis-only execution. Its
`implementation_simulation.models` contains the two `pdk_dir::` vendor references;
`defines` is `["FUNCTIONAL"]`. Acceptance resolves these against the selected PDK
technology directory and compiles them with implementation RTL, **without** the
generated synthesis stub or behavioral top. Timed-model conformance, mapped synthesis
and physical acceptance remain separate evidence. The fast standard-cell −40 °C /
macro −55 °C Liberty difference remains explicit.

## Physical integration handoff

See [PHYSICAL.md](physical/PHYSICAL.md) for the `(40,81)` placement rationale, unchanged
driver/load/timing assumptions, operation matrix, coordinator-only full-run commands,
and the actual independent acceptance collector, failed-attempt chronology and
portable replay/archive checks. P4 physical acceptance is recorded above;
historical C1/C2 evidence below remains unchanged.

## Memory and adapter contract

At a rising edge, enable=0 holds response and storage; enable=1/write_enable=0
registers the addressed word; enable=1/write_enable=1 writes the full 16-bit word.
There is no RAM reset, initialization, mask, or simultaneous read/write. Response
after writes and reads of unwritten words is unspecified. Tests load before read
and never assert those values or depend on simulation poison/power-up zeros.

The bundle top is `tt_um_program_memory`. `clk` clocks everything. `ena && rst_n`
permits commands; low `rst_n` synchronously clears only adapter address/low-data
staging, never the memory. `ui_in[1:0]` commands use `uio_in[7:0]` as payload:

| Command | Edge action |
| --- | --- |
| 0 | Read staged address; response appears after this edge |
| 1 | Stage 8-bit address; RAM disabled |
| 2 | Stage low write-data byte; RAM disabled |
| 3 | Write `{uio_in, staged_low_byte}` at staged address |

Stage address and low byte before committing. `uo_out` shows low response byte
when `ui_in[2]=0`, high byte when `ui_in[2]=1`; this byte selection is combinational.
`ui_in[7:3]` are ignored. `uio_oe` and `uio_out` are always zero (input-only payload
bus). `uo_out` masks to zero while disabled/reset; unmasking reveals retained RAM
response. Inputs must be synchronous; no reset synchronizer is supplied.

The PDK-free Cyclesim tests exercise public Simulation and Implementation flop
circuits and Exact Simulation, all addresses/full-width data, consecutive latency-one
reads, disabled reads/writes and output hold. Resource checks cover both modes and
both selections, optional intent resolution and unsupported Exact shape rejection.
The bundle checker uses read-only Git inspection of the actual source checkout,
two deterministic public emissions, all file/input hashes, separate RTL sets,
resource policy, real macro identity/configuration and original register count. Temporary bundles live
under `.dev/` and are removed after checking. It performs no Git writes.
With `iverilog` and `vvp`, the checker also replays full-address load/read and
adapter/disabled-hold/reset checks against each emitted RTL set independently,
and proves all four selection/source-set combinations reject a corrupted expected
response. A separate public-elaboration core RTL export is replayed against the
same actual vendor models, with consecutive changing-address reads, disabled writes
and full-width overwrites; it also rejects a corrupted oracle. `--require-rtl` makes
missing tools an error; without it their absence is an explicit RTL skip.

## PT.0 verification (2026-10-24)

The following is historical, before public Exact adoption. Its old negative Exact
expectation is superseded by the current commands and adoption evidence below.

Using the exact private ASIC prefix above:

* `dune build -j6 memory/memory_cli.exe` — passed.
* `dune runtest -j6 test memory --force` — passed. Memory Simulation and
  Implementation each checked **1,792 edges** plus inventory/policy/Exact checks;
  the FIFO core checked **7,330 directed + 20,017 seeded edges**.
* `python3 memory/check_bundle.py --cli _build/default/memory/memory_cli.exe
  --source-root "$PWD" --require-rtl` — passed whole-bundle/CLI acceptance and
  **1,280 word checks per generated RTL set**, including negative oracles.
* `dune runtest -j6 .` — passed the existing FIFO wrapper, resolution, catalog,
  CLI, bundle and routing checks. FIFO synthesis/simulation RTL each passed
  **11,429 edges** and a negative oracle. The routing suite reported 21 cases,
  with its opt-in installed-native-provider fixture explicitly skipped.
* `dune build -j6 @all` — passed with the existing Workbench provider SDK also
  selected (needed only for the existing simulation provider adapter):

  ```sh
  OCAMLPATH="$PREFIX/lib:$PWD/.dev/workbench-provider-sdk/lib" dune build -j6 @all
  ```

  Without that extra SDK path, the broad build reports the existing missing
  `hardcaml_workbench_provider` dependency; the memory targets need only the ASIC
  prefix. No dependency build/install, active-generation change, Workbench config
  edit, or physical EDA was needed. Exact's unsupported production mapping is the
   intentional remaining backend blocker at PT.0.

## Public Exact adoption verification (2026-10-24)

Isolated generation: `.dev/asic-sram/generations/ae408e67c800432f9d16cf1d19ed3d74`.
Observed provider base: `bba13079abd519b984e522aa7e898cbef85f4139`.
Captured worktree SHA-256:
`9d8dd740d3ff69990b08ee8e024898ba83a7844400785bb3aeae94b33837255f`.
This is a local development receipt, not a released pin or generator stamp.

* Six-job refresh passed install, compiled external API and Dune link probes.
* Focused build and memory tests passed: **1,792 edges each** for Flops Simulation,
  Flops Implementation and Exact Simulation (**5,376 total**).
* Inventory checks passed for both selections/modes; optional intent resolved both
  present and absent; unsupported 128×16 Exact failed in both modes without fallback.
* Two deterministic emissions per selection passed whole-tree/hash/source-provenance,
  configuration, macro/source-separation and nonempty-output refusal checks.
* Four TT RTL replays passed **1,280 word checks each** (**5,120 total**).
* Direct Exact core vendor-model replay passed **2,048 edges / 1,536 response checks**.
  All **five** RTL replays rejected a corrupted-data oracle. Core RTL has no local
  registers; Exact TT RTL has only the two original 8-bit staging registers.
* No preflight, synthesis or physical EDA ran in assignment C. Coordinator launch
  and mapped-netlist evidence are pending; timed-model and physical gates remain open.

## Coordinator synthesis and mapped gate replay (2026-10-24)

The subsequent installed public preflight passed, and coarse synthesis completed
successfully for the preserved C1 bundle
`480bdd2c6fe04f307fb18de70cebd2fe20c031caeec81d095fa30fe2b317be77`.
Run ID: **`cfd39c581711495cbfd7a150a21715f4`**.
Run root: `_flow_results/sram/runs/20261024T222820714695Z_cfd39c58`.
Standalone preflight:
`_flow_results/sram/operations/20261024T222804311184Z_666bfa56/preflight.json`.

The actual Yosys **0.66** technology-mapped netlist contains:

* **1** `RM_IHPSG13_1P_256x16_c2_bm_bist`, instance `hc_resource_7_program`.
* **16** `sg13cmos5l_dfrbpq_1` flip-flops, matching the original two staging bytes.
* **176** total cells: 175 standard cells plus the SRAM. No flop RAM replacement.
* **0** unmapped cells, inferred latches, synthesis check errors or lint errors.
* **1** lint warning: intentionally unused command input bits `ui_in[7:3]`.

Reported synthesis cell area is **2,182.7232 µm²**, sequential area **783.8208 µm²**.
The synthesis total omits SRAM black-box area: stock SRAM Liberty area alone is
**28,127.104 µm²**. Adding it yields a **30,309.8272 µm² cell-area estimate**, not
placed/routed area, utilization or physical acceptance.

`memory/check_mapped.py` independently inspected the final mapped Verilog and
Yosys JSON/stat histogram, verified the retained bundle hashes and run binding,
then compiled **that actual mapped netlist** with the existing TT replay bench,
vendor SRAM functional models and standard-cell/UDP models. Gate replay passed
**1,280 word checks** and rejected the corrupted expected response (exit 1).
It checks full-address loading/reads, staged output hold, disabled write rejection,
output masking and adapter reset retaining RAM. This is additional mapped-netlist
functional evidence, separate from the earlier RTL-only and direct-core replays.

The unmodified standard-cell timing file first failed in Icarus: its `$setuphold`
delayed-reference outputs are unsupported, leaving flip-flop inputs undriven.
Both failure and diagnostics are retained. The passing replay uses an explicit
derived zero-delay view of only the used vendor cells: original logic and UDP calls
are preserved; `specify` blocks are omitted and the staging cell's delayed
CLK/D/RESET_B nets are wired directly to their corresponding pins. No netlist,
architecture, stock PDK files or SRAM models were edited. **This does not test
timing checks, SDF, timed SRAM conformance or timing closure.**

Durable raw evidence and checksums are under
[`acceptance/sram/`](../../acceptance/sram/README.md). The passing snapshot is
`acceptance/sram/cfd39c58-functional/`; `cfd39c58/` retains the failed unadapted-model
attempt. Source inputs are the bundle's preserved dirty/untracked bytes at example
revision `ac7054395a068c19ced0cd01dd5cc0bcc1ec0015`, not a clean-checkout claim.
The development dependency snapshot is identified above and in the retained receipt;
the old recorded dependency pin is not the linked provider identity. Current docs
and the new gate checker postdate C1; C1 was preserved unchanged.

To repeat inspection and gate replay into a **fresh** evidence directory, without
building or launching EDA:

```sh
python3 memory/check_mapped.py \
  --run-root "$PWD/_flow_results/sram/runs/20261024T222820714695Z_cfd39c58" \
  --bundle "$PWD/.dev/program-memory-exact-c1" \
  --pdk-root "$PWD/_flow_tools/pdk" \
  --provider-generation "$PWD/.dev/asic-sram/generations/ae408e67c800432f9d16cf1d19ed3d74" \
  --preflight "$PWD/_flow_results/sram/operations/20261024T222804311184Z_666bfa56/preflight.json" \
  --evidence-dir "$PWD/.dev/mapped-replay-repeat"
```

No placement, routing, physical power connectivity, DRC, LVS or physical acceptance
is established. Synthesis-only backend restrictions remain in force.

## Final corrected-validator C2 checkpoint (2026-10-24)

The final isolated worktree capture installed generation
`.dev/asic-sram/generations/aa00a92d707447fcba308789e57fa2f6`, including the
corrected OCaml/bridge runtime resource/instance evidence validator. Observed base:
`bba13079abd519b984e522aa7e898cbef85f4139`; captured development snapshot SHA-256:
`8f054fde7462a687139b31564fd823bedb4e0a0f1d7197ea813dcefee27214ca`.
The source capture differs from its observed base; it is not a clean/released pin
or generator stamp. The historical `asic-dependency.json` remains unchanged.

The six-job isolated refresh, `_build_sram -j6` rebuild, focused memory/core/wrapper/
resolution/catalog tests and both-selection bundle checker passed against that
generation, with the previously recorded test counts unchanged. Fresh bundle C2:

```text
.dev/program-memory-exact-c2
4fe842a7c07b94ae9e8e0546210c9273d019fccdca2d5cbf84311948bde64d09
```

The coordinator's public synthesis completed successfully, run ID
**`8b48d7d0818d494f8a9c45000c2bcbbd`**, at
`_flow_results/sram/runs/20261024T225434707093Z_8b48d7d0`.
The run's raw `preflight.json` is retained in the new acceptance snapshot; its two
preflight evidence filenames contain that same run-local report.

Independent actual mapped-netlist replay again passed **1,280 word checks**, and
the deliberately corrupted-data oracle exited **1** on the intended mismatch.
Compiler and positive replay exited **0**. The documented used-cell zero-delay
vendor view and stock SRAM/UDP models were used, with no mapped-netlist edits.
Direct byte comparisons found both **mapped Verilog and metrics identical to C1**:

* One stock SRAM at `hc_resource_7_program`, 16 original staging flip-flops,
  **176 total mapped cells**.
* **0** inferred latches, unmapped cells, synthesis check errors or lint errors;
  **1** intentionally unused-input lint warning.
* Reported synthesis area **2,182.7232 µm²**, sequential **783.8208 µm²**;
  macro Liberty area **28,127.104 µm²**, omitted from the synthesis total.
  Combined **30,309.8272 µm²** is only a cell-area estimate.
* Mapped Verilog SHA-256:
  `a12c6b63e21ed2ab2898bd7c41da3f6dfac768b53382538a7acfb96dd9918575`.

New durable evidence: `acceptance/sram/8b48d7d0-functional/`, with its own run,
manifest, raw configuration/metrics/netlist, source copies, dependency receipt,
models, replay outputs and complete SHA-256 inventory. Verification passed for
**37 files / 595,437 bytes**. Historical C1 verification still passed for
**37 files / 591,602 bytes**; none of those checksum-covered files were modified.

```sh
python3 acceptance/sram/verify.py acceptance/sram/8b48d7d0-functional
python3 acceptance/sram/verify.py acceptance/sram/cfd39c58-functional
```

This final follow-up executed only Icarus acceptance, not new synthesis or physical
EDA. C2 establishes corrected-validator public mapped synthesis and bounded
zero-delay gate functionality. Timed SRAM conformance, STA closure, physical power
access, placement/routing, DRC, LVS and physical acceptance remain unestablished.
