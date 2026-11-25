# Everyday Silver

Silver is optional. For new users, follow the [Silver setup guide](silver.md)
to configure the actual example checkout and launch `ag --standalone`.
The Dune root is this checkout, not a copied project directory.

## Use the configured project

* Select `controlled_fifo / default` in the ASIC launch-target picker.
* Preview `standard / balanced / synthesis` before launching.
* In Testing, choose Controlled FIFO or Memory workloads and select cases.
  Press `R` to run, `e` to edit settings, or `d` to refresh discovery.
* Select a completed VCD in Artifacts; press `w` to view and `e` to export.

The `controlled-fifo` suite's `export-stress` test can generate a 1, 16 or
64 MiB VCD (`trace_mib`). Large traces may require an external waveform viewer.

After source changes, refresh the simulation configuration:

```sh
python3 -B scripts/configure-simulation.py --refresh
```

Reopen Silver after changing machine-local configuration. A regular Dune build
alone does not regenerate the simulation manifest.

## Already prepared launcher installations

Existing users of the prepared-session launcher can continue with:

```sh
python3 -B scripts/silver.py status
python3 -B scripts/silver.py open
```

`open` starts the selected daemon and foreground client, and stops its own daemon
when the client exits. To keep the daemon and jobs alive across client exits,
run in separate terminals:

```sh
python3 -B scripts/silver.py daemon
python3 -B scripts/silver.py client
```

For an external waveform viewer, append `--simulation-viewer /usr/bin/gtkwave`
to the client command. The `scripts/workbench_main.py` launcher name remains
compatible. The launcher has its own explicit build, preparation and publication
commands for maintaining existing selections; see `scripts/silver.py --help`.
Do not publish over an active session or replace an existing selection by hand.

The ordinary [Silver setup guide](silver.md) is the recommended path for new
installations. See its [configuration compatibility section](silver.md#configuration-compatibility)
if migrating old companion names.
