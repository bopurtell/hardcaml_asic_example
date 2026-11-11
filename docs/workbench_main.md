# Everyday Workbench on the actual checkout

`scripts/workbench_main.py` uses the repository root containing `dune-project` as
the editable project. It never creates a copied `project/`. Run the script from
any directory; defaults derive from the script location.

**Local setup verified, 2026-11-11:** prepared and published against the real checkout.
The actual production daemon/client startup, both simulation catalogs and all seven
ASIC endpoint plans passed; the startup smoke submitted no simulation or EDA.
Persistent receipt:
`.dev/workbench-main/verification/startup-20261111T001741Z-bcdf6a98/receipt.json`.
The smoke stopped only its own processes; the main server is left stopped for
manual startup. Older acceptance-store sessions were preserved.

## Integration handoff

The separate simulation helper owns `integration/workbench/checkout_provider.py`,
its persistent manifest and its source-drift/build policy. `prepare --build` calls
`checkout_setup.prepare_simulation` under the launcher's shared example lock,
with the actual root, `_build`, selected generation, stock model root and a bounded
build callback (1800 seconds, 8 MiB combined output). It then produces the regular
FS2 companion handoff at:

```
.dev/workbench-main/simulation/configuration.sexp
```

Without `--build`, an already prepared helper manifest is required. An alternate
configuration is accepted with `prepare --simulation-config /absolute/file`.
The configuration must name an available absolute executable (normally Python),
include the actual checkout's absolute `integration/workbench/checkout_provider.py`
in `provider_args`, and supply `--manifest /absolute/manifest.json`. That regular
JSON manifest must contain `project_root` equal to the actual canonical checkout
root. The launcher validates this handoff without running the router.
No root companion is published if the helper is missing or points to a copied root.

## Prepare, publish, then start

Use the installed compatible compiler environment:

```sh
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_main.py prepare --build
python3 -B scripts/workbench_main.py status
python3 -B scripts/workbench_main.py publish --dry-run
```

Preparation explicitly compiles the current FIFO project, native FIFO provider and
simulator, and workload emit/public executables at `-j2`. It does not provision
tools, build Workbench, run simulations/EDA, publish root companions, or start a
server. Without `--build`, all required current build paths must already exist.

After coordinating with other users of the root checkout, publish separately:

```sh
python3 -B scripts/workbench_main.py publish
```

Publication checks the owner locks and Linux process project/state/discovery
arguments, root-selection environment, working directories and persisted workspace
keys. It does not depend on executable names. Missing lock/state evidence is
reported explicitly as uncertain and fails closed. This is a read-only preflight, not a global reservation
protocol: other launchers must not open the root during publication. The launcher
does not stop, signal or adopt other sessions. All root companion changes require
the exact previously recorded hashes; unknown edits are refused. The first
publication uses the exact baseline captured by `prepare`.

Then, in separate terminals:

```sh
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_main.py daemon
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_main.py client
```

The foreground production daemon selects an available loopback port with `--port 0`
and publishes `discovery/daemon.sexp` using `--discovery-dir`. The client requires
the daemon's lifetime lock and explicit endpoint; it never spawns a daemon. It
opens the actual repository with `--environment inherited`.

The launcher keeps a session lock while supervising its daemon. SIGINT/SIGTERM are
forwarded only to that owned daemon. Client exit leaves the server running.

## Installed selections and persistence

Defaults:

* ASIC generation:
  `.dev/asic-synthesis-envelope-v1/generations/36205ea4748c4972877ac198356d8e44`.
  The directory name is historical; the launcher **removes**
  `HARDCAML_ASIC_SYNTHESIS_TASK_LIMIT` rather than enabling its synthesis-only mode.
  It adds no endpoint restriction.
* SDK: `.dev/workbench-provider-sdk`.
* Prebuilt Workbench pair: sibling
  `hardcaml_workbench/_build_pt8_workbench/default/{daemon,terminal}/main.exe`.
* Root ASIC project executable:
  `_build/default/asics/fifo_demo/cli/project.exe`.
* Results: `_flow_results/workbench/{asic,preparation}`.

`prepare` supports `--asic-generation`, `--sdk-prefix`, `--wb-build-root`, and
`--expected-daemon-sha256` / `--expected-client-sha256`. Installed app bytes and
companion configs live in immutable-by-convention selections under
`.dev/workbench-main/installs/`; `install.json` atomically selects a matching pair.
Earlier selections remain available.

All session state belongs to `.dev/workbench-main/`:

```
install.json                 selected apps, dependencies, config hashes and root
installs/                    app pairs, proposed configs, initial exact backups
published.json               last published companion hashes
publications/                exact pre-publication backups
state/                       normal daemon durable history/artifacts/registry
discovery/                   normal daemon endpoint and lifetime lock
tmp/                         daemon temporary supervisor logs (TMPDIR)
session.lock                 launcher ownership across daemon lifetime
```

Client preferences use the normal `${XDG_STATE_HOME:-$HOME/.local/state}` location.
The server's persistent state and temporary-log root are explicit; there is no
`/tmp` acceptance-store dependency.

The inherited project environment is cleaned of Git repository/config selectors,
captured PT8/Workbench launch selectors, transient SSH/tmux session transports and
the synthesis-only cap. `OCAMLPATH`
contains the selected ASIC and SDK installations; OMP/OpenBLAS/MKL each use one
thread. PATH is reconstructed from the selected switch bin, provider bin, `/usr/bin`
and `/bin`, discarding every inherited PATH entry. Builds pin the actual switch
Dune and `/usr/bin/git` resolution, with a child-process tool/version check.

The explicit launcher/helper build uses `-j2`; this does **not** control the stock
Workbench preparation build (`-j6`), generic build/test (`-j20`), or EDA's normal
six-worker configuration. The launcher does not enforce an aggregate worker/task
ceiling. Run **one heavy operation at a time** and budget all sessions/nested work
within the workspace-wide maximum of 20 jobs. Do not overlap stock preparation,
generic build/test and EDA as if the helper's two-job setting governed them.

## Editing and explicit updates

```sh
# Current source only, with this session's daemon explicitly stopped:
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_main.py build

# Reviewed replacement app pair/configuration/dependency selection:
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_main.py prepare --update --build \
  --expected-daemon-sha256 REVIEWED_DAEMON_SHA256 \
  --expected-client-sha256 REVIEWED_CLIENT_SHA256
python3 -B scripts/workbench_main.py publish
```

Repeated plain `prepare` verifies the existing installation. `build` does not
change apps/configuration. Builds use `_build` and the shared persistent workspace
lock `../.workbench-example-build.lock`; other checkout build helpers should use
that same lock. No ASIC installation is refreshed implicitly.

After a source rebuild, refresh the Testing catalog / ASIC plan as appropriate.
Simulation source-drift policy is owned by the checkout helper; root companion
configuration is fenced by Workbench's explicit discovery contract. Ordinary Fresh
ASIC preparation builds current source and emits its own exact bundle.

Publication backs up all existing regular companion bytes before changing any
file. Each file replacement is atomic, with rollback on caught failure. A crash
can leave `publication-pending.json`: startup then refuses to proceed. Inspect its
expected/previous hashes and exact backup directory, reconcile only those bytes,
and remove the journal only after deliberate recovery. There is no automatic
adoption or silent overwrite of user edits.

Focused launcher verification (inert fixture files, no native daemon or EDA):

```sh
python3 -B scripts/test_workbench_main.py -v
```
