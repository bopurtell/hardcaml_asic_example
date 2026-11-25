# Independent physical timing consumer

## Build and emit

The shared hardware
is `../fixture/timing_specimen.ml`. From the repository root, with `OCAMLPATH`
pointing at an already installed compatible provider's `lib` directory:

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  opam exec --switch=5.2.0+ox -- dune build --build-dir _build -j6 \
  tooling_acceptance/timing/physical/physical_timing_cli.exe
_build/default/tooling_acceptance/timing/physical/physical_timing_cli.exe \
  emit-physical synthesis "$PWD" /tmp/new-physical-timing-bundle
```

The commands above build and emit without EDA. `functional_tb.v` checks 512
observations of the five-register timing specimen; run the emitted RTL replay:

```sh
python3 tooling_acceptance/timing/physical/check_rtl_replay.py /tmp/new-physical-timing-bundle
```

Historical native-tool qualification drivers and acceptance records are archived
separately. RTL replay does not establish timing closure or metastability behavior.
