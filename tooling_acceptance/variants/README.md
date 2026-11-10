# PT8 memory adapter

## Current entry points

From the repository root, with `OCAMLPATH` pointing at an already installed
compatible ASIC provider's `lib` directory:

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  opam exec --switch=5.2.0+ox -- dune build --build-dir _build_migration_tooling -j6 \
  tooling_acceptance/variants/variant_cli.exe \
  tooling_acceptance/variants/verif/conformance.exe
_build_migration_tooling/default/tooling_acceptance/variants/verif/conformance.exe valid
_build_migration_tooling/default/tooling_acceptance/variants/verif/conformance.exe ignored
python3 -B tooling_acceptance/variants/controls/pt8_acceptance.py --help
```

`ignored` deliberately exits 1 after both conformance checks reject the faulty
constructor. `controls/` contains the flat-import phase drivers; workload controls
explicitly import shared helpers from here. Phase drivers retain `_build_pt8`,
with executable paths under `tooling_acceptance/variants` and tests under `verif`.
Historical seals preserve original source paths and hashes in retained evidence;
they may reject changed current sources and must not be used to rewrite past runs.

## Adapter contract

`Variant_memory.project` binds one checked hardware assignment through
`Project.of_variant` to construction. The same constructor registers the actual
`program` RAM in the core and byte-wide TT adapter. Width is 16, read latency 1,
and supported depths are 128 and 256. The 128-word core intentionally decodes the
low seven address bits: address128 aliases address0. The 256-word core decodes all
eight bits. The public port remains eight bits for both so the boundary test can
distinguish them without trusting the declaration.

Resource requirement is a separate argument: explicit Flops, or Exact (only the
stock 256x16 macro is supported). There is no fallback. Existing
`asics/fifo_demo/project/flow_catalog.ml` and
`asics/fifo_demo/project/flow_profiles.ml` supply backend settings; profile
changes do not add hardware parameters or create another launcher system.

The explicitly named ignored-depth negative consumes a valid checked assignment
and constructs depth256 regardless. Its valid hashes are expected to pass the
provider's integrity checks and fail this adapter's semantic conformance oracle.
It is never a supported variant.

No synthesis, place-and-route, STA, PDK probing, Workbench or daemon is needed.
The comparison subcommand calls the installed public comparison API directly.
Source inventories are observations, not compiled-source/P6 attestation.
