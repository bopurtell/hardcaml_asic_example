# Optional Silver integration

Start with a working standalone provider and FIFO build from the [README](../README.md).
Install Silver using its [installation guide](https://github.com/bopurtell/silver/blob/oxcaml/docs/install.md).
The Silver OCaml provider SDK is **only** needed for the simulation adapter, not
for building the FIFO chip or configuring synthesis.

## Synthesis and preparation

```sh
./bootstrap.sh
python3 -B scripts/configure-synthesis.py
ag --standalone
```

For already provisioned tools, skip bootstrap; pass `--toolchain PATH` to setup
if using a nondefault root. The default chip is `controlled_fifo / default`,
with the project-owned catalog `standard / balanced / synthesis`. Quit and reopen
Silver after changing setup, since the running backend caches ASIC configuration.

## Simulation (also install the SDK)

After installing `silver_provider` following Silver's SDK guide, run:

```sh
python3 -B scripts/configure-simulation.py
silver-simulation-setup check --root "$PWD"
ag --standalone
```

Alternatively, `./bootstrap.sh --with-silver` provisions physical tools, then
runs both configuration scripts. This is explicit opt-in to the previous combined
bootstrap behavior. `--check`, `--help` and other nonprovisioning modes are
forwarded to the provider and do not configure Silver even with this opt-in.

Testing lists Controlled FIFO (`controlled-fifo`) and Memory workloads
(`memory-workloads`). Select cases and press `R` to run, `e` to edit settings,
`d` to refresh discovery, and `gd` to open the FIFO declaration in the editor.
Select a completed VCD in Artifacts (`w` view, `e` export). After source changes, use
`python3 -B scripts/configure-simulation.py --refresh`; this updates the manifest
without replacing the existing companion or saved runs. Parallel-capable Silver
can opt in with `--max-parallel-runs 2` on the same script; default is one attempt
at a time.

## Configuration compatibility

For an existing prepared installation, use `python3 -B scripts/silver.py open`.
See [Everyday Silver](workbench_main.md) for prepared/published session setup.

The canonical companions are `.silver/silver-asic.sexp`,
`.silver/silver-preparation.sexp` and `.silver/silver-simulation.sexp`.
Both `silver*.sexp` and `hardcaml-workbench*.sexp` are recognized at the root,
in `.silver/` and in `.workbench/`. Existing copies must have identical bytes;
setup preserves them and refuses conflicts. The ASIC/simulation companions
retain their existing executable selection. Configuration is machine-local and
ignored; saved runs and setup manifests are separate. To migrate names manually,
stop Silver and setup processes, verify identical copies, then move to the
canonical names without overwriting different bytes. Keep project-relative paths,
existing selections, receipts and prior results unchanged. Recover any pending
publication before moving files.
