# Accepted physical SRAM evidence — P4

Run `be961b2c95f74c81ad6af81ca4d2b269`, external postcheck
`0553f6d19c8f42d28c057fc65ed23510`, 2026-10-25.
Bundle identity: `fa38d9064dffdf2ec1578c79c2e8890eba81bf704af460e85fcc6031b707d53c`.
The provider receipt identifies a captured development worktree, not a released pin.

## Practical standalone commands

After extracting the archive, from this directory:

```sh
python3 verify.py .
python3 replay_snapshot.py --snapshot "$PWD" --output-dir /tmp/sram-replay-NEW
```

The first command needs only Python's standard library. The second also needs
installed `iverilog` and `vvp`; it compiles only retained files and writes outside
the snapshot. Positive replay must pass 1,280 word checks; `+negative` must exit 1
on the deliberately corrupted first expected low byte. The snapshot and all replay
inputs are hash-checked before/after. A fresh output directory is required. No PDK,
provider, original workspace paths, Docker or EDA are needed for these two commands.

Absolute paths in raw public receipts are provenance, not portable replay inputs.
Re-running physical tools or the original public-record checker against its external
inputs still requires the identified toolchain, PDK, generation and original run.
This archive is evidence plus a portable gate replay, not a complete EDA installation.

## Accepted scope

- One unchanged stock `RM_IHPSG13_1P_256x16_c2_bm_bist`, actual instance
  `hc_resource_7_program`, latency one, only the original 16 staging flip-flops.
  `dlygate*` cells are combinational hold-delay cells, not additional state.
- Physical placement/routing and verified supply contacts/public pins, real-GDS
  KLayout/routing/overlap checks and all-corner extracted setup/hold/slew/cap/fanout.
- Abstract macro-boundary LVS with schematic CDL, 109 matched macro pins; **not
  internal-device LVS**.
- Public external TT precheck and final-netlist zero-delay gate replay.
  **No SDF or timed SRAM conformance, and no IR/EM adequacy claim.**
- Raw Magic DRC count remains **3**. Exact four-control stock wide-LEF-obstruction
  evidence dispositions all three; unclassified count is zero. Raw reports and
  diagnostic-only LEFs are retained; stock implementation collateral is unchanged.

Worst setup slack: **11.246561 ns**. Worst hold slack: **0.223533 ns**.
The fast standard-cell −40°C / macro −55°C model difference remains explicit.

## Layout

`summary.json`, `run.json`, `preflight.json`, `provider-receipt.json` and `bundle/`
bind source/configuration/generation identities. `physical-checks.json`, `flow/`,
`final.gds`, `mapped.v`, `metrics.json` retain raw physical evidence and final views.
`postchecks/` retains the original public postcheck, TT reports/logs and original /
reviewed zero-delay used-cell models. No mapped-netlist or stock SRAM model edits.

`supplemental/current-compiled/` proves the original public Icarus-13 executable
rejects corrupted expected data, using its recorded local image and a read-only
run mount. `supplemental/portable-replay/` and `restoration.json` prove a tar-restored
snapshot alone compiled/replayed with host Icarus 12 (positive and negative).
`original-artifacts-unchanged.json` records before/after hashes of the original
run/PDK/bundle inputs and compiled executable.

`failed-attempts/` preserves compact original P1/P2/P3 failed records, exact bundles,
provider receipts, diagnostics/logs and metrics. Large prior final views are hashed
instead of duplicated. P1 failed at native PDN; P2 failed LVS/electrical gates; P3
finished native execution but failed public Magic classification. None is relabeled.

`checksums.json` covers every other file. Verify it before interpreting or replaying
the evidence. Existing C1/C2 synthesis snapshots remain separate and unchanged.
