# Timing tooling qualification

The shared five-register hardware is in `../fixture`, with its provider-independent
Cyclesim check in `../fixture/verif`. This directory owns the basic project and CLI.
Named-flow and physical consumers are siblings.

From the repository root, using an already installed compatible ASIC provider:

```sh
export OCAMLPATH="$HARDCAML_ASIC_GENERATION/lib${OCAMLPATH:+:$OCAMLPATH}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
opam exec --switch=5.2.0+ox -- dune build --build-dir _build -j6 \
  tooling_acceptance/timing/fixture/verif/core_test.exe \
  tooling_acceptance/timing/basic/timing_cli.exe \
  tooling_acceptance/timing/named_flow/named_timing_cli.exe \
  tooling_acceptance/timing/physical/physical_timing_cli.exe
_build/default/tooling_acceptance/timing/fixture/verif/core_test.exe
_build/default/tooling_acceptance/timing/basic/timing_cli.exe \
  emit-scalar "$PWD" /tmp/new-timing-bundle
```

The core check itself needs only Hardcaml. Emitting bundles and preparing named
plans require no EDA or provisioning. Use a new output directory for emission.
Run `dune runtest tooling_acceptance/timing/fixture/verif` for the core test.
Historical qualification drivers and sealed evidence are kept in the development
archive, not required for current emission.
