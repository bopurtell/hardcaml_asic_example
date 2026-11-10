# Timing tooling qualification

The shared five-register hardware is in `../fixture`, with its provider-independent
Cyclesim check in `../fixture/verif`. This directory owns the basic project, CLI,
and authored Python/Tcl harness. Named-flow and physical consumers are siblings;
phase-specific Python drivers live in `../controls` and keep flat sibling imports.

From the repository root, using an already installed compatible ASIC provider:

```sh
export OCAMLPATH="$HARDCAML_ASIC_GENERATION/lib${OCAMLPATH:+:$OCAMLPATH}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
opam exec --switch=5.2.0+ox -- dune build --build-dir _build_migration_tooling -j6 \
  tooling_acceptance/timing/fixture/verif/core_test.exe \
  tooling_acceptance/timing/basic/timing_cli.exe \
  tooling_acceptance/timing/named_flow/named_timing_cli.exe \
  tooling_acceptance/timing/physical/physical_timing_cli.exe
_build_migration_tooling/default/tooling_acceptance/timing/fixture/verif/core_test.exe
_build_migration_tooling/default/tooling_acceptance/timing/basic/timing_cli.exe \
  emit-scalar "$PWD" /tmp/new-timing-bundle
python3 -B tooling_acceptance/timing/controls/pt7named_acceptance.py --help
```

The core check itself needs only Hardcaml. Emitting bundles and preparing named
plans require no EDA or provisioning. Use a new output directory for emission.
Drivers retain their original phase-specific build-directory names, with targets
under `tooling_acceptance/timing`.

Historical closeout/seal drivers intentionally refer to retained `acceptance/`
and `.dev/` receipts, original input IDs, and captured source snapshots. Those
receipts describe past executions. Their original-source hash assertions are not
new-layout acceptance checks and may reject changed current sources. Do not
rewrite or regenerate historical receipts to make them match this relocation.
