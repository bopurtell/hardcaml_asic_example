# Controlled FIFO FS2 provider

The native project-owned `test_provider.exe` adapter starts the existing standalone
`fifo_sim.exe` with the same arguments as the retained Python reference provider.
Only the adapter links `hardcaml_workbench_provider` (`Wire`, `Validation`, `Runner`);
the library handles protocol validation and event plumbing, not tests or checkers.
The simulator and ordinary CLI/Dune tests remain independent of Workbench.

The simulator uses the real `Controlled_fifo` Cyclesim
DUT and `Fifo_test_support.directed` / regression traffic with the independent
ordered-list model. Its checks follow `ip/controlled_fifo/verif/cyclesim/fifo_test.ml`: pre-edge snapshots
(except unspecified power-up state), pre-edge acceptance, and post-edge snapshots.
Existing CLI/Dune tests retain their original single-int PRNG seed behavior.

Catalog: suite `controlled-fifo`; cases `directed`, `seeded`; seed default `42`;
parameters (both required): `cycles` = `64`, `4096` (default), `20000`;
`checker` = `normal` (default), `mismatch`. `cycles` controls only seeded traffic;
directed always runs the complete existing directed generator. Either case can
be selected alone, or both in requested order. ASIC inputs must be empty.

FS2 seeds are canonical decimal uint64, including `18446744073709551615`.
Both adapters split all 64 bits into **four little-endian 16-bit words**, supplied to
`Random.State.make` by `regression_with_seed_words`. No high bits are truncated.
This expanded mapping intentionally differs from the historical single-int CLI
mapping, even for small seeds. Reproducibility is for the same OCaml toolchain.
Reports retain the exact decimal seed and the four words.

`checker=mismatch` flips only the expected post-edge occupancy at zero-based edge
17. It never changes the DUT, input sequence, or VCD. The full simulation continues,
reports the cycle/phase/field/expected/observed/model value, stimulus and recent
history, and emits semantic Failed while the provider exits zero. Native `.vcd`
and `.sexp` reports are genuine simulator/checker output. Progress counts include
initial clear and final drain/underflow, so totals may exceed `cycles`.

Explicit installation (no dependency refresh, ASIC builds, tests, or daemon work):

```sh
python3 scripts/install-fifo-simulation.py --build \
  --with-switch /absolute/hardcaml_workbench/scripts/with-switch.sh \
  --build-dir /tmp/opencode/native-provider-example --jobs 6
# Or install both already verified native executables:
python3 scripts/install-fifo-simulation.py \
  --provider /tmp/opencode/native-provider-example/default/ip/controlled_fifo/verif/simulation/test_provider.exe \
  --simulator /tmp/opencode/native-provider-example/default/ip/controlled_fifo/verif/simulation/fifo_sim.exe
```

Builds require the separately packaged `hardcaml_workbench_provider` library.
For development on this machine, consume the persistent package prefix through
`OCAMLPATH="$PWD/.dev/workbench-provider-sdk/lib"` when building from the project
root; no global opam switch installation is required. The standalone simulator
target does not depend on this package. A fresh machine must install/build the
provider package first; this development package is not yet published to opam.

The helper copies only `test_provider.exe` and `fifo_sim.exe` into a new
persistent `.dev/fifo-simulation/<generation>/` before adopting the root companion
`hardcaml-workbench-simulation.sexp`. Ownership is recorded by exact config SHA256
in `.dev/fifo-simulation-install.json`. Missing ownership or any config edit is
refused before build/install by default. ASIC configuration and results are never accessed.
Old generations remain available to already-running sessions. Discovery and run
never build. The installed config directly names the native provider, with empty
prefix arguments; the simulator defaults to its adjacent `fifo_sim.exe`. Python
`provider.py` and the shared `integration/workbench/wire.py` stay in the source tree as equivalence references and
are never copied into native generations. Installation is an explicit adoption step.

For an intentional migration of an edited, previously installed config, pass
`--adopt-config-sha256 EXPECTED` alongside the prebuilt executable arguments above.
`EXPECTED` must be the lowercase SHA256 of the exact current config bytes. This
option requires the existing ownership manifest, verifies its original generation
checksums and original config snapshot, and refuses changes to the owned provider
executable or arguments. The config must contain exactly the known five fields;
valid specified discovery/run timeouts are preserved. It does not claim unrelated
configurations or bypass missing ownership.

Each install writes a persistent `.dev/fifo-simulation-receipts/<generation>/`
receipt before publication, including exact previous config and ownership backups
(when present), the new config and ownership snapshot, and checksums. Files and
directories are flushed to disk; config and ownership publication use atomic
replacements with a final concurrent-edit check and an installer lock. The journal
is `prepared` before publication and `published` after both replacements succeed.
If interrupted between replacements, the prepared receipt retains the bytes needed
to inspect or recover the transaction; ownership refusal still applies on retry.
Receipts are separate from the two-executable native generations. No daemon restart
or simulation run is performed by installation.

```sh
/absolute/test_provider.exe --simulator /absolute/fifo_sim.exe discover --protocol-version 1
/absolute/test_provider.exe --simulator /absolute/fifo_sim.exe run --protocol-version 1 \
  --request /absolute/request.sexp --events /absolute/events.sexp \
  --artifact-dir /absolute/existing-artifacts-directory
```

`--simulator PATH` is an optional prefix argument before `discover`/`run`; omit it
for the adjacent default. Both executables may also be invoked directly without
an installed configuration. Run private installer transaction tests with
`python3 scripts/test-install-fifo-simulation.py`; these never adopt the root config.
Compare discovery, events, native stdout, report/VCD bytes and invalid-request
rejection against the retained Python reference with the command below. It also
installs the real prebuilt binaries into a temporary private project to exercise
the adjacent-simulator default; the source project's config is never adopted.

```sh
python3 scripts/test-native-fifo-provider.py \
  --provider /absolute/test_provider.exe --simulator /absolute/fifo_sim.exe
```

Example request (the attempt ID comes from the caller):

```scheme
((protocol_version 1)
 (attempt_id fifo-manual)
 (selection
  ((suite controlled-fifo) (cases (directed seeded))
   (seed 18446744073709551615)
   (parameters ((checker normal) (cycles 64)))
   (asic_inputs ()))))
```

Invalid/duplicate fields, cases, parameters, noncanonical seeds and nonempty ASIC
inputs fail before events or artifacts are written. Runtime simulator errors are
process failures, never manufactured passing cases. Events append, flush, and use
contiguous sequence numbers. Provider stdout retains native progress/failure logs.
