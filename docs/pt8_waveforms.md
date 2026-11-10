# PT.8 opt-in interface waveforms

**Final corrected capture accepted:** `.dev/asic-pt8-workbench/session-waveforms-final-01`.
Strict supported-format validation and failed-inspection waveform suppression are
fixed; six durable tests pass. Final direct pair, source-only Plan and fresh native
Testing JSON-cursor→VCD flow pass with final client `2c301d20…`. See
[final commands, receipts and hashes](../../hardcaml_workbench/docs/pt8_waveform_final_acceptance.md) and
[correction receipt and hashes](../../hardcaml_workbench/docs/pt8_waveform_producer_corrections.md).
Session02 results below are preserved historical acceptance.

The reusable `scripts/pt8_workloads.py` retains historical no-dump behavior by
default. `bench(..., capture_waveform=True)` adds only explicit interface dump
statements; `simulate(..., capture_waveform=True)` runs the same actual Icarus
execution in its private simulation directory, validates `waveform.vcd`, and
retains the byte/hash/time/signal descriptor `waveform.json`. The WB Runner opts
in. No memory initialization, hierarchy dump or stock-model edits are added.

FS2 publishes `CASE-waveform` (kind `trace`, media `text/vcd`) attached to the
case and subject to normal FS2 attempt prefixing/hash-bound byte transport.
The independent `CASE-result-reference` JSON contract is unchanged and remains
the authoritative Workloads handoff. Invalid/failed/cancelled capture never
announces a successful waveform artifact.

Signals: clock `clk`, enable `ena`, active-low **write command** `rst_n`, address
`ui_in[7:0]`, data byte `uio_in[7:0]`, response `q[15:0]`. Memory write data is
the address concatenated with that byte. `rst_n` is not an initialization reset.
Undefined response values remain X. The final viewer draws known lanes at time0
and marks only the unknown `q` lane “X/Z in window; no graph”; its signal list
still shows X. Move the cursor to2595000 (1ps ticks), the first defined
read response, to render all six signals.
Zoom out to inspect successive enable/write/address/read cycles.

## Captured private session

New source-complete `.dev/asic-pt8-workbench/session-waveforms-02` uses the
unchanged pinned ASIC provider from `session-final-review-01`. Its fresh Flops
and Exact pass, each producing64,078 bytes /6 signals /6028 changes over1307
cycles, matching historical functional traces and counters. The first rejected
validator attempt remains in immutable `session-waveforms-01`.

To run the final accepted capture in separate terminals (leave the foreground
daemon running):

```bash
opam exec --switch=5.2.0+ox -- python3 -B scripts/pt8_workbench_launch.py daemon --session .dev/asic-pt8-workbench/session-waveforms-final-01
opam exec --switch=5.2.0+ox -- python3 -B scripts/pt8_workbench_launch.py client --session .dev/asic-pt8-workbench/session-waveforms-final-01
```

Use **Workloads: Launch fresh PT.8 workload**, choose a positive Testing case,
keep seed34097 and confirm launch. Select the case, then **Simulation: Open
embedded waveform CASE implementation interface waveform**. The selected case's
Artifacts pane also offers `w`/`W` for embedded/dedicated Waveforms views. Use
**Inspect workload result** separately for JSON evidence.

## Verification

- `python3 -B scripts/test_pt8_waveforms.py -v`: dump default preservation,
  actual Icarus VCD syntax, budgets and negative publication subcases.
- `scripts/pt8_waveform_acceptance.py`: fresh direct real pair, exact historical
  trace/counter equality, copied-byte/hash identity, stock-model failure, actual
  SIGTERM cancellation and140 protected-file preservation checks.
- `scripts/pt8_waveform_native_acceptance.py`: production Testing form launches
  a fresh Exact run, actual Open waveform parses signals, reads real hash-bound
  transport, moves cursor and renders waves at the first defined response, then
  opens the dedicated Waveforms workspace. Uses only its owned private runtime.

Full concrete artifact paths, hashes, commands and failure history are in
[Workbench producer handoff](../../hardcaml_workbench/docs/pt8_waveform_producer_handoff.md).
All simulation is functional Icarus; EDA allocation0. Setup reused the existing
provider generation and built only the isolated example, switch5.2.0+ox,
`dune build -j 2 --build-dir _build_pt8_workbench` under the shared example lock.
