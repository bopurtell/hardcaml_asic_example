# Memory workload verification

The workload emitter and latency-one adapter live here. The Python runtime in
`support/` provides directed stimulus, RTL replay, receipt writing and waveform
validation for the optional Silver integration.

From the repository root, with `OCAMLPATH` pointing at an already installed
compatible ASIC provider's `lib` directory:

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  opam exec --switch=5.2.0+ox -- dune build --build-dir _build -j6 \
  tooling_acceptance/workloads/workload_emit.exe \
  tooling_acceptance/workloads/workload_public.exe
_build/default/tooling_acceptance/workloads/workload_emit.exe \
  "$PWD" flops /tmp/new-workload-bundles
```

These build/emission commands need no EDA or provisioning. For waveform
validation and failure-publication tests, run `python3 -B scripts/test_memory_waveforms.py`.
The optional Silver simulation integration belongs to `integration/workbench`.
Historical qualification programs and receipts are archived separately; legacy
schema identifiers remain unchanged for compatibility.
