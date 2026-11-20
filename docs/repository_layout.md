# Repository ownership and storage

Current source organization after the 2026-11-10 migration. The
[migration record](migration_plans/ownership_layout.md) explains implementation and
verification; [Workbench continuation](migration_plans/workbench_continuation.md)
describes session boundaries and configuration follow-up.

## Ownership first

An IP owns its RTL and verification. A parent ASIC can import the IP's model and
stimulus without moving them into global infrastructure. Each ASIC owns its top,
chip-target/flow declarations and system-level environment. Reusable drivers, monitors,
or checkers belong in a root `verif/` only when they actually serve multiple owners;
there is currently no need for an empty shared verification framework.

```text
ip/controlled_fifo/
  rtl/                       Hardcaml hardware
  verif/
    support/                 Independent list model and stimulus
    cyclesim/                Standalone core verification
    simulation/              Simulator and simulation-provider adapter
asics/
  fifo_demo/
    rtl/                     TT top/wrapper
    project/                 fifo_chip.ml declaration, flow catalog/profiles, Fifo_asic facade
    cli/                     chip.exe and stage recipe client
    verif/                   Wrapper and declaration/catalog checks
      bundle/                Emission verification and RTL replay
  program_memory/
    project/                 Combined core/TT adapter/chip target
    cli/                     Standalone chip.exe for program memory
    verif/                   Memory checks, replay benches, snapshot replay
    physical/                Physical harness, packaging, evidence documentation
tooling_acceptance/
  timing/
    fixture/                 Five-flop core; its verif/ checks reset and latency
    basic/                   Timing-intent integration and local probes
    named_flow/              Same fixture through named-flow/profile APIs
    physical/                Same fixture through physical qualification
    controls/                Cross-route native/API controls
  variants/                  Parameterized memory API fixture; verif/ and controls/
  workloads/                 Workload API clients and controls/
integration/workbench/       Composite provider, shared protocol, integration helpers
scripts/                     Repository setup and verification entry points
acceptance/                  Retained evidence, not the active hardware source tree
```

### Chip target migration (WB-082)

The Dune root is the **project**. Each registered **chip target** has an
`asics/<id>/cli/chip.exe` entry in `hardcaml-asic-targets.json`. The two
`project/` library directories retain their Dune library names. Use
`Fifo_asic.chip_target`, `Program_memory.chip_target`, or `Sram_budget.chip_target`
to construct a `Hardcaml_asic.Chip_target.t`; the old `.project` functions remain
aliases. `fifo_chip.ml` holds the former FIFO `project.ml` declaration.

Existing `asics/fifo_demo/cli/project.exe` and
`asics/program_memory/project/memory_cli.exe` build the same binaries as the new
paths. Use `chip list --json` on the FIFO CLI instead of `project chip list --json`.
`project_name` in protocol output and `project_executable` in Silver config keep
their wire spellings. Source inventories change with source moves: derive a fresh
plan identity before emitting or running; historical bundles keep their old paths.

The FIFO IP library owns its `clock` input and logic. Its TT wrapper connects
that input to `clk`, and the chip declaration sets the period (48 MHz). Program
memory also targets 48 MHz; the SRAM-budget target declares 20 ns. Clock timing
belongs to each chip, not the enclosing project or its catalog. See the
[build and enumeration commands](../README.md#chip-target-cli).

Verified against the local `../hardcaml_asic` build: the provider listed and
invoked both registered executables; after removing the program-memory entry in
a disposable project, its standalone CLI still built and described the chip.
The two legacy executable paths produced byte-identical binaries to their new
counterparts. `scripts/test_chip_routing.py` checked FIFO synthesis planning,
program-memory timing emission, both SRAM-budget synthesis variants, their
resolved clocks and target-specific source inventories. The FIFO core/wrapper,
program-memory behavioral tests and both SRAM-budget RTL replays passed. These
checks cover elaboration and emitted bundles, not physical timing closure.

## Verification versus tool qualification

* FIFO ordering is IP verification.
* Behavior through the TT pins is ASIC verification.
* Timing closure/physical implementation of an ASIC is ASIC implementation
  verification, even when checks use reusable tool APIs.
* Named-flow provenance, resource-selection API behavior, archive fidelity, and
  Workbench protocol/session behavior are tooling acceptance.

The timing family is **not FIFO timing collateral**. It owns a tiny separate
five-register qualification circuit. Basic, named-flow, and physical integrations
are different routes through the tools using the same hardware fixture.

## Old-to-new path map

| Before migration | Current path |
| --- | --- |
| `lib/` | `ip/controlled_fifo/rtl/` |
| `test_support/` | `ip/controlled_fifo/verif/support/` |
| `test/` | `ip/controlled_fifo/verif/cyclesim/` |
| `simulation/` simulator/provider | `ip/controlled_fifo/verif/simulation/` |
| `simulation/{wire,workbench_provider}.py` | `integration/workbench/` |
| `asic/tt_wrapper.{ml,mli}` | `asics/fifo_demo/rtl/` |
| Other `asic/` files | `asics/fifo_demo/project/` |
| `bin/` | `asics/fifo_demo/cli/` |
| `asic_test/` | `asics/fifo_demo/verif/` |
| Authored `acceptance/{check_bundle.py,export_trace.ml,replay.v}` and Dune rules | `asics/fifo_demo/verif/bundle/` |
| `memory/{program_memory.ml,memory_cli.ml,dune}` | `asics/program_memory/project/` |
| `memory/test/`, replay benches, bundle/mapped/snapshot checks | `asics/program_memory/verif/` |
| Memory physical checking, packaging, records, PHYSICAL/EVIDENCE docs | `asics/program_memory/physical/` |
| `memory/README.md` | `asics/program_memory/README.md` |
| `timing/timing_specimen.{ml,mli}` | `tooling_acceptance/timing/fixture/` |
| `timing/core_test.ml` | `tooling_acceptance/timing/fixture/verif/` |
| Remaining `timing/` files | `tooling_acceptance/timing/basic/` |
| `named_timing/` | `tooling_acceptance/timing/named_flow/` |
| `physical_timing/` | `tooling_acceptance/timing/physical/` |
| `variants/`, including `test/` | `tooling_acceptance/variants/`, with `verif/` |
| `workloads/` | `tooling_acceptance/workloads/` |
| `scripts/pt7_tool.py`, `pt7c*.py`, `pt7named*.py` | `tooling_acceptance/timing/controls/` |
| `scripts/pt8_workloads*.py` | `tooling_acceptance/workloads/controls/` |
| `scripts/pt8_workbench*.py`, `pt8_waveform*.py` | `integration/workbench/` |
| Other `scripts/pt8*.py` | `tooling_acceptance/variants/controls/` |

The script entry points `scripts/workbench_dev.py` and `scripts/workbench_git.py`
remain available. Shared dependency/bootstrap/headless utilities remain in scripts.
Library names such as `controlled_fifo`, `fifo_test_support`, and `fifo_asic` remain
stable. The ASIC project copies the wrapper source through Dune to preserve its
existing facade; the timing routes similarly share their qualification core.

## Storage is separate from source ownership

| Location | Contents and writers |
| --- | --- |
| `.dev/` | Dependency/simulation installers and setup helpers write selected local installations, receipts, and locks. Historical development scripts also stored experiments/results here. |
| `_flow_tools/` | Installed provider provisioning writes managed tool runtime and collateral when explicitly requested. |
| `_flow_results/` | Project/provider execution writes default bundles, operations and flow evidence. Explicit configurations may select other result roots. |
| `_build*/` | Dune writes build outputs. All root build variants are ignored. |
| `acceptance/` | Deliberately curated historical evidence and reproduction packages. Some packages own their own verifiers. |

For a development store specifically, `state/` is daemon-owned durable
history/artifact/registry storage, `discovery/` identifies the daemon endpoint and
lifetime lock, and `client-state/` stores client preferences. These are distinct
from installed provider generations and from EDA results.

Captured manifests/receipts identify historical bytes and selections. They do not
change when active source is reorganized. Avoid mechanically replacing paths or
hashes in retained evidence to make it resemble today's source tree.
