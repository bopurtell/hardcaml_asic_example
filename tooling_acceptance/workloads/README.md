# Workload API qualification

The workload emitters and latency-one test adapter live here; Python phase drivers
live in `controls/`. They explicitly import shared receipt/comparison helpers from
`tooling_acceptance/variants/controls` and dependency helpers from `scripts`.

From the repository root, with `OCAMLPATH` pointing at an already installed
compatible ASIC provider's `lib` directory:

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  opam exec --switch=5.2.0+ox -- dune build --build-dir _build_migration_tooling -j6 \
  tooling_acceptance/workloads/workload_emit.exe \
  tooling_acceptance/workloads/workload_public.exe
_build_migration_tooling/default/tooling_acceptance/workloads/workload_emit.exe \
  "$PWD" flops /tmp/new-workload-bundles
python3 -B tooling_acceptance/workloads/controls/pt8_workloads.py --help
```

These build/emission commands need no EDA or provisioning. The phase driver keeps
`_build_pt8_workloads`, with executable targets under `tooling_acceptance/workloads`.
Workbench/simulation integration belongs to `integration/workbench`.
Retained `acceptance/pt8-workloads` and `.dev` result paths, captured input IDs,
and historical seals describe their original executions and are not relocated.
