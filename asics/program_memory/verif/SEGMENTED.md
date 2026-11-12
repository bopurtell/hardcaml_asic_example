# Stock SRAM segmented tooling consumer

`segmented_consumer.exe` is a verification consumer of the public ASIC project API.
It declares flow `stock256-r0`, profile `qualification`, with fresh endpoints from
Synthesis through Timing. It uses the existing exact program-memory design and
physical settings, not the main FIFO project selection.

Build against a provider with the bounded `sram_segmented1` scope, using its
isolated library prefix explicitly. Example (from this repository):

```sh
OCAMLPATH="$PREFIX/lib" opam exec --switch=5.2.0+ox -- \
  dune build -j10 asics/program_memory/verif/segmented_consumer.exe \
  @asics/program_memory/verif/segmented-preparation
```

The alias is PDK-free: it checks catalog/description, all six plans, exact
preparation/export linkage, output integrity, stale preview rejection, legacy
commands and unsupported Signoff. It does not launch EDA.

Public Workbench-facing commands:

```text
flow list --json
flow describe --flow stock256-r0 --json
flow plan --flow stock256-r0 --profile qualification --endpoint timing --source-root ROOT --json
flow emit --flow stock256-r0 --profile qualification --endpoint timing --source-root ROOT --results-root RESULTS --expected-plan-identity ID --json
prepare --source-root ROOT --results-root RESULTS --json
```

Plan identities bind the actual source root and source inventory. Recompute previews
after changes; do not reuse an old capture's plan against new source. The legacy
`prepare ROOT ENDPOINT` and `export ROOT NEW_BUNDLE ENDPOINT` forms remain supported.
`flow run` and Signoff are rejected; the provider owns segmented execution.

Real installed qualification and Workbench launch/reopen evidence are described in
[the provider guide](../../../../hardcaml_asic/docs/guides/segmented-sram.md) and
[Workbench release record](../../../../hardcaml_workbench/docs/sram_segmented_release.md).
The original main FIFO configuration and installations were preserved.
