# Repository ownership and storage

An IP owns its RTL and verification. Each ASIC owns its top, target and flow
declarations, and system verification. An ASIC can import an IP's model and
stimulus without moving them into shared infrastructure.

```text
ip/controlled_fifo/
  rtl/                       Hardcaml FIFO hardware
  verif/
    support/                 Independent model and stimulus
    cyclesim/                Standalone core verification
    simulation/              Optional Silver simulator/provider adapter
asics/
  fifo_demo/
    rtl/                     Tiny Tapeout top and wrapper
    project/                 FIFO chip declaration and catalog facade
    flows/                   Named methodologies and profiles
    cli/                     Standalone chip executable
    verif/                   Wrapper, resolution and catalog tests
      bundle/                Bundle emission and Verilog replay
  program_memory/
    project/                 Memory core and chip declaration
    cli/                     Standalone chip executable
    verif/                   Memory verification and replay
    physical/                Physical harness and evidence checking
  sram_budget/               Multiple RAM requests sharing a macro budget
tooling_acceptance/           Separate timing, variants and workload fixtures
integration/workbench/       Optional Silver integration
scripts/                     Setup, headless client and verification utilities
docs/                        Current user guides
```

## Chip targets

The Dune root is the project. `hardcaml-asic-targets.json` registers chip target
IDs and executable paths. `controlled_fifo` is the default chip; its default
variant emits `tt_um_controlled_fifo`. The FIFO owns its clock input and RTL;
the wrapper connects the clock to `clk` and the chip declaration sets the period
(48 MHz). Clock timing belongs to each chip, not to the project catalog.

The FIFO's `asics/fifo_demo/cli/chip.exe` and the program-memory target's
`asics/program_memory/cli/chip.exe` are standalone entry points.
See the [build and enumeration commands](../README.md#chip-target-cli).
The older executable paths `asics/fifo_demo/cli/project.exe` and
`asics/program_memory/project/memory_cli.exe` remain compatibility aliases.
If Silver has a saved `fifo_demo/default` selection, select
`controlled_fifo/default` in its launch-target picker.

## Verification and tooling

* FIFO ordering, reset and overflow behavior are component verification.
* Behavior through TT pins is ASIC verification.
* Timing closure and physical checks are implementation verification.
* Named-flow, resource selection, archive and protocol checks are tooling verification.

The timing fixtures exercise a separate small five-register circuit, not the FIFO.

## Generated output

| Location | Purpose |
| --- | --- |
| `_build*/` | Disposable Dune build outputs |
| `_flow_tools/` | Explicitly provisioned physical tools and collateral |
| `_flow_results/` | Generated bundles, operations and execution records |
| `.silver/` | Optional machine-local Silver configuration |

Keep generated outputs separate from authored source. Plan and bundle identities
are content-derived; source changes require a fresh preview rather than editing
an existing bundle. Retain the exact returned execution record when reporting
results.
