# Registered program-memory SRAM testbed

## Build and verify

This specimen lives at `asics/program_memory/`. The combined core, TT adapter,
and chip target remain in `project/program_memory.ml`; `cli/chip.ml` is its
standalone CLI. Core/wrapper tests, replay benches,
`check_bundle.py`, `check_mapped.py`, and `replay_snapshot.py` live in `verif/`.
Physical capture/package/check harnesses and their shared contracts live in
`physical/`. The conventional executable targets are:

```sh
dune build --build-dir _build -j6 \
  asics/program_memory/cli/chip.exe \
  asics/program_memory/verif/memory_test.exe
```

For standalone catalog discovery, run
`dune exec asics/program_memory/cli/chip.exe -- flow list --chip program_memory --json`.
This executable rejects other chip IDs. Program memory's `stock256-r0` flow
uses a hand-written catalog; Duplicate Profile previews a declaration snippet
to register manually and does not change `project/program_memory.ml`.

## Resource preparation and selection

`chip prepare` invokes public `Preparation_service.run_cli`, constructing
the chip target inside the allocated closure and passing `on_phase` to
`Chip_target.prepare_resources`. `preview` computes the same implementation evidence
without publication; `resources` returns a nonpublishing inventory (default
Implementation, explicit `--simulation` for behavioral elaboration).

Selection now also accepts `fallback` (`Exact_or_flop_fallback`); the explicit
`--depth 128` fixture has no exact stock macro, exercising real flop fallback or
an Exact rejection without rounding. Default depth remains 256 and the accepted
SRAM declarations/evidence retain their existing operation/intent behavior.

Independent of the FIFO, this is a real public `Single_port_ram.create` consumer:
**256 words × 16 bits, one shared read/write port, read latency one**, stable
resource ID **`program`**. `program_memory.ml` contains the typed full-width core,
a small byte-wide TT adapter, and the chip declaration. It uses production
`Technology.ihp_sg13cmos5l`, never an experimental mapping or local macro RTL.

This is the ongoing production-style SRAM consumer. Exact now selects stock
`RM_IHPSG13_1P_256x16_c2_bm_bist` through the production backend, retaining the
original cycle contract and **no new architecture registers**. The existing two
8-bit TT staging registers remain consumer-owned. The CLI requires independent
`--selection flops|exact` and `--operation synthesis|hardening` arguments for both
`check` and `emit`. OCaml `Program_memory.chip_target ?operation` retains its old defaults
when omitted: Exact Synthesis, Flops Hardening.

The Exact declaration includes optional consumer intent using
`Macro_intent.tt_cmos5l_r0 ~resource:(Resource.Id.of_string_exn "program")
~x_um:42. ~y_um:81. ~halo_um:2. ()` for Synthesis, passed with `Flow.librelane ~macros`.
Explicit Hardening instead declares the candidate **`(40,81)` R0**, same 2 µm halo.
`Program_memory.chip_target ~with_macro_intent:false Exact` explicitly omits that intent;
the CLI uses the declared intent. The actual emitted instance is
**`hc_resource_7_program`**. R0, halo and power mappings are declarative intent;
physical validation is a separate step. A compatible provider supports
Exact Hardening with schema 2 / `fresh_full` and generated
`physical/macro-plan.json` / `physical/pdn.tcl`, strategy
`cmos5l_m4_edge_access_v1`; schema-1 synthesis remains available. On the physical
macro path only, `Tt_cmos5l.overrides ~without` removes `RUN_KLAYOUT_DRC`,
`FP_PDN_VPITCH`, `FP_PDN_VWIDTH` and `FP_PDN_MULTILAYER`: the provider generates
these facts. All other selection/operation paths retain their template defaults.
The declaration alone is not physical evidence.

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

For the PDK-free behavioral tests, run `dune runtest asics/program_memory/verif`.
For the segmented flow plan and emission checks, run
`dune build @asics/program_memory/verif/segmented-preparation`. See
[segmented verification](verif/SEGMENTED.md) for the API and scope.
The [physical checks](physical/PHYSICAL.md) describe current evidence tools.
Historical evidence is preserved separately in the development archive, with its
original filenames and receipts; it is not a prerequisite for building this example.
