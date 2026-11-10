# Repository ownership and storage

Current source organization after the 2026-11-10 migration. The
[migration record](migration_plans/ownership_layout.md) explains implementation and
verification; [Workbench continuation](migration_plans/workbench_continuation.md)
describes session boundaries and configuration follow-up.

## Ownership first

An IP owns its RTL and verification. A parent ASIC can import the IP's model and
stimulus without moving them into global infrastructure. Each ASIC owns its top,
project/flow declarations and system-level environment. Reusable drivers, monitors,
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
    project/                 Declaration, flow catalog/profiles, Fifo_asic facade
    cli/                     Project CLI and stage recipe client
    verif/                   Wrapper and declaration/catalog checks
      bundle/                Emission verification and RTL replay
  program_memory/
    project/                 Combined core/TT adapter/declaration and CLI
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

`program_memory.ml` intentionally still combines its core, adapter, and project:
this migration changes ownership paths, not hardware architecture or public APIs.

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
