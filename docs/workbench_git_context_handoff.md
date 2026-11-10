# Scoped development Git context — B correction handoff

2026-11-05. Implements Workbench `docs/development_git_context_recovery.md`.
The owner's active stable daemon/store are NOT refreshed, stopped or patched.
Old failed operations/bundles and all revision validation remain unchanged.

## Contract

`scripts/workbench_git.py` is captured as `GENERATION/tool-bin/git`, with a regular
`git-context.json` alongside it. The latter records schema1, the absolute real Git
executable and SHA256, and an exact canonical source-root→owner-metadata mapping.
Only the fixed private `project` and that generation's immutable `source` root are
mapped. This is source comparison context, not a commit containing those snapshots.

Base daemon/provider environments have NO GIT_DIR/GIT_WORK_TREE or other repository
selectors. The dispatcher cleans inherited repository/index/object/discovery/config
injection variables, while preserving unrelated environment, stdout/stderr, argv and
the real command's exit/signal status via exec. GIT_OPTIONAL_LOCKS=0 and controlled
global/system-config suppression apply to all metadata reads. Real Git is pinned in
`inputs.git` (optional explicit `--git ABS`) and `git_context.real_git[_sha256]`;
setup/launch verify its digest, and the dispatcher verifies it before every exec.

The dispatcher parses separate `-C PATH` options left-to-right, including relative,
absolute, empty and repeated/nested -C. It compares the FINAL canonical effective
cwd with exact mapped roots, never a path prefix. A matching root gets scoped
GIT_DIR/GIT_WORK_TREE only for that Git process. Collateral/other/unknown roots use
real Git's own repository discovery with repository selectors removed. Source
subdirectories are not mapped implicitly. Malformed attached -C options/missing
arguments retain real Git's own diagnostics/status. Supported harmless global flags
are explicit in the helper. Global --git-dir/--work-tree/--bare/--namespace/-c/
--config-env and unknown/ambiguous overrides reject rather than guessing or changing
argv semantics. Subcommand query arguments such as `rev-parse --git-dir` are intact.
No output/revision is synthesized; no check is waived; no checkout is changed.

The router and launcher use the same sanitization. The helper is part of both
suites' relevant-source inventory. An existing private project needs explicit
`prepare --refresh --update-owned-support` to add the missing helper and update
only baseline-matching router/setup/test code. Unknown user edits still refuse.
All regular-config journal/rollback and lifetime-lock protections remain in force.

## Legacy captures and owner recovery

`status` and idempotent `prepare` retain the exact selection/history but report a
`git_context_diagnostic` for a legacy global-selector capture. Future launches with
the corrected launcher refuse that unsafe capture and explain explicit recovery;
an already-running daemon is not signalled, restarted or mutated.

**Run only AFTER the owner explicitly stops its own foreground daemon**, from the
example checkout (not performed by B against the user store):

```sh
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_dev.py prepare \
  --refresh --update-owned-support --git /usr/bin/git
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_dev.py status
# Only when the owner chooses to resume:
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_dev.py daemon
# Separate terminal:
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_dev.py client
```

Use the SAME --store for a private verification store. No new user demo root is
required. Refresh preserves project/state/history/artifacts/preferences and all old
generations; it never automatically retries the failed synthesis operation.

## Initial real private acceptance

First14-test pass: `/tmp/opencode/workbench-dev-b-hr3hfxkv/store/test-evidence/result.json`.
Installed private generation available immediately for C:
`/tmp/opencode/workbench-dev-b-hr3hfxkv/store/generations/eeb80a48d090461bb810ee74aceba21b`.
Manifest: `.../store/manifest.json`; context: `GENERATION/tool-bin/git-context.json`.

* Actual support-tools HEAD: d66cf179e7bc4d296362ab7e2e3b344dc3c4f665.
* Actual PDK HEAD: 2bbec755dc67ca3db0261c3d6163e15735d66710.
* Both real collateral `status --porcelain -- README.md` reads are clean; source,
  fixture and collateral indexes remain unchanged.
* Real standalone installed provider `preflight ... --native --json` on a fresh
  private source-only bundle: exit0, ready=true, issues=[]; metadata only, zero
  container probes, no synthesis/P&R/EDA stage execution.
* A real independent wrong-revision Git fixture: preflight exit1, ready=false,
  explicit observed/requested support-tools revision mismatch (also missing that
  fixture's floorplan collateral). No revision or evidence bytes were edited to
  make the negative pass. Fixture objects/index were constructed with Python in
  private storage; no Git write/configuration command was run.
* Existing native Discover, FIFO normal/mismatch, both actual PT8 simulations,
  source Plan/build/emission, ordinary project tests, cancellation and preservation
  gates continue to pass in independent private stores.

Detailed receipts: `.../test-evidence/scoped-git/receipt.json` and
`.../test-evidence/installed-git-preflight/receipt.json`. C owns independent
reproduction against the original retained failure and any production Dockerized
metadata/preflight acceptance. B's native metadata pass does not claim synthesis.

## Final tightened acceptance and installed private legacy upgrade

**All14 tests PASS** at:
`/tmp/opencode/workbench-dev-b-v68x1aej/store/test-evidence/result.json`.
The final Git controls use valid separate repeated -C arguments, require successful
exit0 as well as empty porcelain output, preserve real Git's error129 for malformed
attached -C, and check the source-owner index as well as fixture/collateral indexes.
The installed preflight positive explicitly requires exit0, ready=true and no issues;
the wrong-revision negative explicitly requires exit1, ready=false and the genuine
observed/requested revision issue. Both pass. Missing-helper migration is exercised:
ordinary refresh refuses, then explicit baseline-checked support migration adds it.

Final receipts:

* `.../test-evidence/scoped-git/receipt.json`
* `.../test-evidence/installed-git-preflight/receipt.json`
* `.../test-evidence/launcher/native-discover.json`
* `.../test-evidence/preservation.json`

An actual older B-owned PRIVATE store with legacy global selectors was explicitly
refreshed (not the user's active store):

```sh
opam exec --switch=5.2.0+ox -- python3 -B scripts/workbench_dev.py \
  --store /tmp/opencode/workbench-dev-b-jzc4uvlt/store \
  prepare --refresh --update-owned-support --git /usr/bin/git
```

**Final installed capture for C:**
`/tmp/opencode/workbench-dev-b-jzc4uvlt/store/generations/f889ee7589844720ae8379e0c2db0816`.
It is selected by that private store's `manifest.json`. The ordinary source root is
`/tmp/opencode/workbench-dev-b-jzc4uvlt/store/project`; context roots are exactly
that path and `GENERATION/source`. The captured real Git is `/usr/bin/git`, SHA256
`eb54b535467e0975c1284d4c4d08eea779aeb248a5d34b02e2ee171382e22201`.

`receipts/f889ee7589844720ae8379e0c2db0816/source-migration-result.json` records
the actual baseline hashes for the router/launcher/test update and the absent-helper
addition. Existing private source edits and old generations remain. No source
directory was recopied. Selected app hashes remain client
`896cee9b6546be5c5d7fcd132306a55cf33cbc43d1c25edbd7cea9c467bd7a42`, daemon
`ec0108fd3ae65ac8bc8113462bfc1eb4dcdcbecf6410c144fbc982113f495a38`.

The explicit private-refresh output reports `git_context_diagnostic: null`, empty
source drift for both suites, no missing sources, and a base environment whose only
Git variables are the three controlled read-only settings. The active owner store,
its selected generation/configs/history, original failed evidence and daemon550084
were NOT refreshed, stopped, rewritten or queried by this correction. C can now
independently inspect this pinned private capture or prepare its own private store;
no B production edit or test workaround is needed to exercise the dispatcher.
