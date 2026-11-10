# PT8 independent example — preparation and acceptance procedure

> **Historical procedure:** source/driver paths below predate the ownership
> migration. Use the [current layout map](repository_layout.md); preserve the
> original retained evidence and captured identities.

2026-10-29. C owns only `variants/`, `scripts/pt8*`, `docs/pt8*`,
`acceptance/pt8`, `.dev/asic-pt8` and `_build_pt8`. The pre-work seal is
`acceptance/pt8/preservation-before.json`; it covers tracked sources, untracked
physical/named histories, retained evidence and ignored provider stores/selectors.

## Adapter and semantic checks

`variants/variant_memory.ml` declares depth128/256, width16, read_latency1 through
the public Hardware_variant schema. Complete assignments enter Project.of_variant;
the checked factory argument supplies Single_port_ram.Config and address decoding.
Policy is a separate explicit argument. Existing `asic/flow_profiles.ml` and
`asic/flow_catalog.ml` remain the backend knobs and are copied by Dune, not edited.

The independent `variants/test/conformance.ml` oracle verifies actual registered
resource identity, request/shape, policy and selection. Five positive functional
simulations check explicit Flops128/256 in Implementation and Simulation, plus
Exact256 in Simulation. A separate sixth simulation exercises a deliberately
ignored depth128 assignment against depth256 hardware. Its request and behavior
checks must both reject, and that invocation exits1. The negative is not a
supported hardware variant. The emitted negative bundle demonstrates separately
that a valid declaration/hash is not a semantic conformance certificate.

Every positive simulation loads/reads the full declared capacity, checks before-
and after-edge registered latency, disabled reads/writes, final-address overwrite,
and the distinguishing address0/address128 alias boundary. Exact128 is rejected
in both elaboration modes; the valid integer schema's unsupported depth192 hole
is rejected in the consumer factory. No fallback, banking or shape rounding.

## Installed workflow

Use `python3 -B scripts/pt8_acceptance.py PHASE --attempt UNIQUE_NAME`.
Capture only after A/B are ready; capture invokes switch5.2.0+ox, the shared ASIC
lock and explicit6-job nested build/install/probe commands with individual logs.
All subsequent phases require the exact new `--generation` directory, never a
historical provider/current selection. Build uses `_build_pt8`, `-j6` and the
shared example lock. No EDA command exists in this harness.

Phases: `capture`, `build`, `functional`, `emit`, `compare`. The matrix driver
`scripts/pt8_matrix.py --attempt NAME --generation DIR --emission EMIT_ATTEMPT`
uses only the installed comparison API and native public CLI. It asserts:

- Fresh Flops128/256 hardware differences, policy-only Exact256 and existing
  backend-profile-only settings; unsupported Exact128 rejects.
- Historical named area/delay attempts remain distinct despite equal netlists;
  absent parameters are unavailable, with no inferred metadata.
- Accepted physical vs itself, and named synthesis vs physical, preserve separate
  execution, resource, timing and acceptance outcomes and retained metric context.
- Source corruption and rebound claims on copies reject, with no history changes.
- API/CLI JSON parity, no winner, no workload claim, no ineligible metric delta.

Every comparison invocation is traced with strace process/file syscalls: exactly
one process (the public CLI exec-replaces itself with the installed native helper),
no child tools/renderers, and no write-capable filesystem
syscalls. The source seal is independently reverified at closeout. Comparison
exit0 means readability, not successful hardware/physical acceptance or a winner.

## Status

Installed acceptance is complete: see [actual results](pt8_final.md), including
retained failed preparations and the Exact methodology-plan limitation. New bundles
uniformly use existing public catalog resolution, Project.render_result and
Bundle.publish, so no Exact plan support is implied. No Protemu/Workbench consumer selection or P6
compiled-source attestation follows from declared source observations.
