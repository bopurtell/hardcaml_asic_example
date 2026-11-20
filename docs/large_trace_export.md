# Large FIFO VCD export acceptance (WB-040)

The `controlled-fifo` suite includes `export-stress`, a real Hardcaml Cyclesim
case using the independent FIFO list checker. Select `trace_mib=1`, `16`, or `64`
(default 1). Other cases ignore this parameter; `cycles` is ignored by this case.
This belongs in the existing suite because it exercises the same DUT/provider,
with a deliberately larger trace rather than a new verification backend.

Stimuli and checking stream one edge at a time; the generator retains only the
model and eight diagnostic edges. Less than 4 KiB of legal final VCD comment
padding reaches the exact selected byte size without truncating an event.
64 MiB is Silver's maximum supported simulation artifact, not an unlimited-size
test. The full trace is too large for the embedded waveform viewer (8 MiB cap).

## Start Silver

From `hardcaml_asic_example/`, in separate terminals:

```sh
# Terminal 1: foreground server
opam exec --switch=5.2.0+ox -- python3 -B scripts/silver.py daemon
```

```sh
# Terminal 2: client, optionally with external GTKWave handoff
opam exec --switch=5.2.0+ox -- python3 -B scripts/silver.py client \
  --simulation-viewer /usr/bin/gtkwave
```

The matching app pair was rebuilt from `silver/` and published to the existing
main launcher on 2026-11-17. No further prepare/publish step is needed for that
selection. For future simulation source edits, stop the server and explicitly run
`opam exec --switch=5.2.0+ox -- python3 -B scripts/silver.py build`.

## Generate and export through Testing

1. Open Testing via the `Space c c` command palette. Focus Catalog and press `d`
   to refresh discovery; review and accept changed defaults with `u` if requested.
2. Choose **Controlled FIFO / independent list checker** (`n`/`p`). With `j`/`k`
   and `x`, select only `export-stress`; inspect the subset in the launch form.
3. Press Enter, set `trace_mib` to `64`, leave `checker=normal` and `seed=42`, and
   submit. The ordinary `cycles` value does not affect this case.
4. Wait for Passed. In Artifacts select `export-stress.vcd`.
5. Press **`e`** for export only. **F8** shows the completed path; **F9** recopies
   it to the clipboard. Record elapsed time and the artifact digest from Detail.
6. Press **`v`** for export followed by external viewer launch. This starts the
   configured executable with the verified local file as its argument. GTKWave
   should open the FIFO waveform; add signals in GTKWave to inspect activity.

`e` needs no GUI. `v` launches on the host running the Silver **client**, not on
the provider host or automatically on your laptop. Over SSH, a remote GTKWave
needs working graphical display access. Clipboard copying transfers the path,
not the VCD file. Silver's `w`/`W` embedded viewers are separate from this handoff.
Silver observes successful process creation, not whether a GUI subsequently
opens successfully; manually confirm the actual window and waveform.

## Cancel an in-flight export

The current client has no dedicated Cancel Export button or command. Its streaming
export cancels when the owning attempt/project/client identity changes.

1. Have at least two attempts in Testing history (run the 1 MiB case first if needed).
2. On the 64 MiB attempt, select the VCD and press `v` (or `e`).
3. While the export is running, Tab to **Attempts**, then use `j`/`k` to select a
   **different attempt**. Merely focusing a different pane is insufficient.
4. Confirm no viewer opens for the abandoned export and its newly created
   `hardcaml-export-partial-*` directory disappears from the client's temporary
   directory (`TMPDIR`, normally `/tmp`). Existing verified exports remain.
5. Return to the large attempt and export again; it should not report a stuck
   active-export reservation.

The abandoned attempt's notice is intentionally fenced, so switching attempts
need not display a cancellation toast. Do not use Ctrl-C/process termination as
the cleanup test: process-crash cleanup is outside the declared guarantee.
Cancelling a simulation job is a different operation from cancelling file export.

## Direct fixture and verification evidence

A generated fixture is retained locally (ignored by Git):
`.dev/wb040-export/export-stress-64mib.vcd`. It is not automatically registered as
a Silver attempt; use the Testing case above to generate a provider-owned artifact.

Reproduce directly after building:

```sh
mkdir -p .dev/wb040-export
_build/default/ip/controlled_fifo/verif/simulation/fifo_sim.exe \
  export-stress 42 42,0,0,0 64 \
  .dev/wb040-export/export-stress-64mib.vcd \
  .dev/wb040-export/export-stress-64mib.sexp normal
wc -c .dev/wb040-export/export-stress-64mib.vcd
sha256sum .dev/wb040-export/export-stress-64mib.vcd
```

Verified 2026-11-17: exactly 67,108,864 bytes, 1,258,782 edges, 15,105,379
passing checks; GTKWave `vcd2fst` parsed the complete file successfully.
SHA-256: `a4662d87338898d3b328a56a9d74692adf2cfc21701c62d21c96c0a0a9b8952e`.
The actual composite provider also discovered the case and ran its 1 MiB selection
successfully, emitting its waveform/report and Passed events.

After a seed-42 64 MiB UI run, compare the exported file's size/SHA-256 against
the registered artifact's Detail and optionally the direct fixture above. Record
real HTTP export timing, cancellation cleanup, and visible GUI success in WB-040;
fixture generation alone does not complete that manual acceptance.
