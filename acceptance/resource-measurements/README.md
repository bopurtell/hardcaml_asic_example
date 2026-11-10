# PT.5b independent example acceptance

Status: **installed public schema-2 acceptance passed** on 2026-10-27.
`installed-final/receipt.json`: **15 tests, 0 failures/errors/skips**.
`closeout-final.json` verifies focused results, full example-suite/FIFO logs,
executable identities, archive hashes and protected-state preservation.
`raw-01.json` separately records the earlier four raw capture checks.

`installed-02/` and `closeout-01.json` are preserved byte-for-byte but superseded:
they predate A/B's independent-review fixes. Final acceptance hashes those earlier
records before/after, plus the original augmented capture receipt.

The new `accepted-live-01/` directory is an augmented **byte-copy capture**, not
a new physical execution. `run/` retains the complete historical physical-p4
base and adds original accepted-run post-route reports and their contained inputs.
`capture.json` records every source/destination SHA-256, byte length, provenance
role, and protected history/configuration/provider-pointer inventories.
Original absolute paths, historical checksums, run and checker records stay intact.
No original record is resealed. `run/capture-origin/` preserves the live identity
records separately; it does not fabricate a producer checkpoint.

Actual capture: **333 files / 111,847,065 bytes**. `capture.json` includes the
complete 276-file historical-tree inventories before/after, configuration hashes
and existing provider-current symlink identities/timestamps. All protected state
was unchanged. The four checks verify capture/source closure, accepted identity
and unchanged base bytes, geometry/gross bounds, and sampled raw path/unit inputs.
They do not execute a public provider or count as measurement-parser acceptance.

Reproduction from the example checkout (each destination must be new):

```sh
python3 -B scripts/check_resource_measurements.py \
  --capture acceptance/resource-measurements/accepted-live-NEW
python3 -B scripts/check_resource_measurements.py \
  --verify-capture acceptance/resource-measurements/accepted-live-NEW \
  --receipt acceptance/resource-measurements/raw-NEW.json
```

The verifier currently requires the original local sources to remain available,
so it can prove source/copy equality and protected-state preservation. The retained
bytes and source mapping are portable; original-path availability is not a future
public inspector requirement. Generated unit `.lib` files are plaintext ASCII
Liberty; capture preserves their original bytes.

**Correction, 2026-10-27:** the earlier gzip-without-extension description was
incorrect. Python binary inspection verified original/captured equality for all
three libraries: prefix `6c 69 62 72` (`libr`), not `1f 8b`; fast/slow/typical sizes
40188/40188/40187 bytes. Stage-56 SDFs are also plaintext (`(DELAYFILE`), and none
of the nine captured `.lib`/`.sdf` files has gzip magic. The tool's binary-file
refusal did not establish compression. The provider parses plaintext units.
The raw verifier only conditionally decompresses actual gzip bytes; it does not
assert the libraries are gzip. Its inaccurate comment is superseded by this note,
with scripts, frozen snapshots, receipts and raw history preserved unchanged.
See the guide for full verification values. Synthetic gzip-report negatives are
separate, intentional malformed-input cases.

See [`../../docs/resource_measurements.md`](../../docs/resource_measurements.md)
for asserted measurement scopes, oracles, limitations and execution rules.

## Installed public acceptance

Isolated generation: `.dev/asic-pt5b/generations/4848a66eeda54751b12d645ee9bcd5c4`.
Source snapshot: `03b13eb7dd2b2918594754c19b41cbc5fe5042f309a9f2f91eae221b6aed4f4f`.
This is a dirty development-byte capture, not a clean-source or P6 stamp.
Closeout observes the moving ASIC source still matches the tested snapshot.
The library consumer is the existing thin `resource-realization/installed_api.ml`,
rebuilt in `_build_pt5b`; it implements no local parser/reconciliation.

After isolated capture/activation and serialized explicit `-j6` builds:

```sh
python3 -B scripts/check_resource_measurements.py --public \
  --provider .dev/asic-pt5b/current/bin/hardcaml-asic-flow \
  --consumer _build_pt5b/default/acceptance/resource-realization/installed_api.exe \
  --schema1-provider .dev/asic-pt5/generations/dd1ec9002cdc40f2936488cedd9eb0fe/bin/hardcaml-asic-flow \
  --output-dir acceptance/resource-measurements/installed-NEW
```

Use a new output directory. `tested-script.py` freezes the executed harness;
numbered stdout/stderr and receipts retain commands, exits, identities, disposable
mutation digests and unittest outcomes. Public commands run with no tools in PATH
and nonexistent toolchain. No external PDK lookup is performed.

The passing run asserts exact geometry, LEF-class sums and six gross ratios;
186 sampled paths/372 macro electrical points, precise slack/slew/load, blank
columns and the fast analysis/model-corner distinction. Varied raw report values
and core bounds prevent constant-output false positives. Schema-2 and genuine
frozen-provider schema-1 archives retain **every advertised reference byte**:
respectively **76 and 56 refs**, each hashed inside `reports.tar.gz`.
Real historical schema-1 evidence also source-replays against original physical-p4.
Report renders fresh schema 2 without modifying stored schema-1 results; archive
verifies and retains the stored schema-1 assertion's advertised sources.

`installed-01/` is retained honestly: 10 tests, 5 assertion failures and 1 error.
Harness expectations were corrected for provenance-contradiction CLI 1, fresh
schema-2 report rendering, and negative slack incorrectly still marked `MET`.
No provider workaround or ASIC source edit was made by C.

Final independent review regressions cover both missing-primary-arrival attacks
(including removal of the true endpoint), no data-role `A_CLK`, nested-only unit
spoof, empty/garbage/gzip report diagnostics with preserved valid max paths,
partial-LEF native-area contradictions, post-PIN duplicate attributes,
unclosed/mismatched LEF nesting, and `END COMPONENTS_WRONG`. Physical diagnostic
hash chains are rebound explicitly; semantic rejection is distinct from tamper.
Truthful partial/failed observations also pass source replay. A/B own the larger
56/73 feature suites and attempted-point-budget coverage; those are not counted
as C's independent public cases.

`suite-final.stderr`: full example suite passed (unittest groups 11 + 24 + 21,
directed/seeded FIFO/wrapper, memory and positive/negative RTL replay).
`fifo-final.stderr`: **5 standalone FIFO-emission compatibility tests passed**;
this is emission compatibility, not macro physical/timed qualification.

```sh
python3 -B acceptance/resource-measurements/record_closeout.py --final \
  --receipt acceptance/resource-measurements/closeout-NEW.json
```

The recorder verifies retained logs/identities and writes a new closeout; it reruns
no tests/builds. Existing approved PT.5 Workbench/app configuration and pre-existing
provider selections are unchanged; only the explicitly isolated PT5b store was created.

`provider-final-binaries.json` records all 18 installed dispatcher/native companion
hashes. The dispatcher hash is unchanged across these two captures; the final
resource-inspection companion is
`84e2c061cf9aa45ee1fc2c232481ab0268a6555d8196f4340cbb13a8ee167ac9`.
The final installed API consumer is
`edb23745eb57f295a9c7c05b9b87ad3f8e44a14ef7e25968359b6795a305219f`.
The approved application provider remains explicitly PT.5.
