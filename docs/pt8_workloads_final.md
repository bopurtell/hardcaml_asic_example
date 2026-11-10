# PT.8 workload slice C — final reviewed-corrections installed handoff

2026-11-05. **Final installed reader acceptance passes after the independent-review
corrections, including F2 postcheck discovery fencing and B-A1 flow-alias
compatibility.** This completes C's bounded installed example acceptance for PT.8
library scope. The exact commands and evidence below establish that scope; they do
not claim exhaustive verification or Protemu consumer adoption.
All evidence is new under `acceptance/pt8-workloads/`, with the isolated provider
and bundle store `.dev/asic-pt8-workloads` and build `_build_pt8_workloads`.

## Final reader capture and actual installed results

Final reader generation:
**`1d3e1195ba4f45fb93eb986ca23cfb75`**, under the isolated
`.dev/asic-pt8-workloads/provider/generations/` directory.

| Provenance | SHA256 |
|---|---|
| Captured provider snapshot | `86d7b71e7992429cf84b239ae70fe7fd3fbbd2b449227760ef64e0dc57e2d466` |
| Provider receipt | `96f2984fbcfc74f9d0943076719ca7bfbffd167305b0f61e1fa97d08f3a45d44` |
| Final `execution/results/variant_comparison.ml` | `348ed85a31dd82e4c6ec748cafae358f4cc5080b157e35de2fc13131317d1a29` |
| Final `execution/results/retained_file.ml` | `6f69c0bea1f987f0c48c908264d3ad195db5f49a07cd624ec32e5a0369729fcc` |

`capture-final-01-nested` retains the exact captured sources and seven nested
build/install/query/probe receipts. `build-final-01` rebuilds against that installed
generation. All Dune operations use explicit six-job limits, `_build_pt8_workloads`,
switch5.2.0+ox and the shared per-checkout locks, including the nested capture.
The final seal explicitly receives the reviewed **348ed85…** source hash rather than
using the superseded intermediate correction pin as an acceptance expectation.

Passing final installed evidence under `acceptance/pt8-workloads/`:

- **`acceptance-final-01/assertions.json`**: complete public verification/negatives
  and API/CLI parity; all seven matched workload metrics remain comparable with
  zero deltas.
- **`controls-final-01/assertions.json`**: complete installed association/control
  matrix, retaining functional failures and unavailable/confounded performance.
- **`regressions-final-01/assertions.json`**: repeated same-process directory
  rejection has zero FD growth; all six late opposite workload/target raw-source
  mutations reject in the final API and CLI.
- **`discovery-alias-final-01/assertions.json`**: six actual installed F2 discovery
  rejections (API/CLI × initially absent checks directory, empty directory, existing
  unmarked child). The pipe-synchronized mutation occurs at workload result open5,
  after target replay, and creates a failed `postcheck.json`; each query exits2,
  produces no stdout, and reports `final postcheck discovery generation changed`.
  Clean controls first pass. A permitted internal flow-directory symlink then
  passes API and CLI with equal outcomes, while a late retarget to byte-identical
  contents rejects twice with `final raw source alias changed`.

These additional discovery/alias controls use a small **synthetic disposable coarse
fixture**, sourced from the final captured provider's test helper (source hash is
in its receipt), plus the verified original workload bundles. They make no new
physical execution or performance claim. Stable controls have traced read-only
queries and complete API/CLI parity; mutation controls use the explicit test-only
openat interposer and pipe handshakes, never sleeps. B separately reports its
retained historical matrix passing1860 files/18 native deltas; that provider result
is supporting review context, not a new C physical measurement.

**Simulation producer remains `59aeb673765d4ef5b9308eb611f8cf0f`.**
`final-review-baseline-01/reuse.json` freshly verifies original `simulation-04`
bytes, source equality and regenerated identical testbenches before reader rebuild.
No bundle emission, Icarus/vvp, synthesis/P&R/STA or other EDA was repeated.
Additional simulator executions remain **zero**; the initial12 historical simulator
processes remain exactly those previously retained.

Final receipt: **`final-reviewed-receipt.json`**, with exact reader and producer
identities, source/executable/model hashes, commands, all final passing results and
the evidence inventory. It supersedes reader acceptance in both earlier receipts;
**`final-receipt.json` and `final-corrected-receipt.json` are unchanged**.
`preservation-final-review-01/preservation.json` verifies the original141450 files/
1678 symlinks and the new intermediate-history baseline7720 files/2 symlinks,
**zero changes**. `final-review-baseline-01` also preserves the intermediate docs
and executables. All earlier captures/receipts/failed attempts remain intact.

Actual final commands (example root; evidence directories below already exist):

```sh
python3 -B scripts/pt8_workloads_corrected.py baseline --output final-review-baseline-01 \
  --prior-reader-receipt final-corrected-receipt.json
python3 -B scripts/pt8_workloads.py capture --attempt capture-final-01
GEN="$PWD/.dev/asic-pt8-workloads/provider/generations/1d3e1195ba4f45fb93eb986ca23cfb75"
python3 -B scripts/pt8_workloads.py build --attempt build-final-01 --generation "$GEN"
python3 -B scripts/pt8_workloads_acceptance.py --attempt acceptance-final-01 \
  --simulation simulation-04 --generation "$GEN"
python3 -B scripts/pt8_workloads_controls.py --attempt controls-final-01 \
  --simulation simulation-04 --generation "$GEN"
python3 -B scripts/pt8_workloads_regressions.py --attempt regressions-final-01 --generation "$GEN"
python3 -B scripts/pt8_workloads_discovery_alias.py --attempt discovery-alias-final-01 \
  --generation "$GEN" --capture capture-final-01-nested
python3 -B scripts/pt8_workloads_corrected.py verify --output preservation-final-review-01 \
  --baseline final-review-baseline-01/baseline.json
python3 -B scripts/pt8_workloads_seal.py --output final-reviewed-receipt.json \
  --generation "$GEN" --acceptance acceptance-final-01 --controls controls-final-01 \
  --capture capture-final-01-nested --preservation preservation-final-review-01/preservation.json \
  --regressions regressions-final-01 --producer-reuse final-review-baseline-01/reuse.json \
  --discovery-alias discovery-alias-final-01 \
  --expected-comparison-sha256 348ed85a31dd82e4c6ec748cafae358f4cc5080b157e35de2fc13131317d1a29
```

## Intermediate correction history (retained, superseded reader)

The **intermediate reader provider** was
`.dev/asic-pt8-workloads/provider/generations/187374d595024c7da15756979957f907`.
Its exact source snapshot and seven nested command receipts are retained under
`capture-corrected-01-nested/`. `build-corrected-01` rebuilt the public shim and
emitter against it; **no bundle emission or functional simulation was repeated**.
Corrected snapshot SHA256:
`93c907e2124d82c74bba99fa631c7e5e70c89f68353884340764d7d8bc591105`;
provider receipt SHA256:
`fd6b5ccef55f7327ef49facef11165b06a95b058f9af33e1ce656c22a44bc564`.
Capture/build remained serialized under the shared ASIC/example locks, switch
5.2.0+ox, explicit six-job Dune, `_build_pt8_workloads` throughout.

Confirmed captured corrections:

| Reader source | SHA256 |
|---|---|
| `execution/results/variant_comparison.ml` | `fdb4b6275ed23e8febe0411a00dfc611fbffb50c242553f5b3cd0f2c8603c053` |
| `execution/results/retained_file.ml` | `6f69c0bea1f987f0c48c908264d3ad195db5f49a07cd624ec32e5a0369729fcc` |

The original `simulation-04` producer remains generation
**`59aeb673765d4ef5b9308eb611f8cf0f`**, with its original source/executable provenance
below. The corrected reader is **not** reattributed as the producer of that RTL or
those simulation attempts. `correction-baseline-01/reuse.json` verifies all four
executions byte-for-byte against the original final seal, checks every declared
constructor/adapter source against the original bundle, matches actual RTL bytes
to `synthesis_sources`, and regenerates identical testbench text. Original emitter
and shim executables and the prior documentation are copied there before rebuild.
The constructor, RTL, stimulus, testbench, oracle, models, tool settings and raw
simulation observations are unchanged. Additional Icarus/vvp executions: **zero**.

New passing installed receipts:

- `acceptance-corrected-01/assertions.json`: full public inspection, stable/stale
  rechecks, semantic/evidence negatives and entire API/CLI response parity;
  seven matched workload metrics remain comparable with zero deltas.
- `controls-corrected-01/assertions.json`: full installed API/CLI control and
  association matrix passes against `simulation-04`.
- `regressions-corrected-02/assertions.json`: the two specific provider fixes pass.
  **500 directory-rejected public `Workload_result.inspect` calls in one process**,
  after one warmup, retain **5 descriptors before / 5 after, growth0**. The actual
  error is `in_channel_of_descr : Invalid argument`, exercising conversion cleanup.
  Separate process/file/network tracing confirms this query remains one process.
- The same regression receipt contains **six deterministic late-mutation
  rejections**: API and installed CLI each reject changed opposite-side workload
  trace, target manifest and target RTL. A test-only `LD_PRELOAD` openat probe stops
  at workload result open7 (right deep recheck, after left deep recheck); the parent
  changes a disposable left source and releases a pipe, without sleeps. Same-size
  trailing-whitespace replacement preserves parseability/semantics. Each invocation
  exits2 with **`comparison final raw source generation changed`** and no stdout.
  Clean copied controls first pass. All originals remain untouched. These late
  probes use test interposition, separate from the ordinary traced public queries.

`regressions-corrected-01` is retained: an initial append mutation correctly rejected
with the final captured byte bound, but the harness expected the hash-fence wording.
The passing02 uses equal-size whitespace replacement to exercise the exact raw-hash
diagnostic. This was a harness refinement, not a provider failure or simulator rerun.

The new **`final-corrected-receipt.json`** supersedes only reader acceptance, binds
the exact corrected provider receipt/source and executable hashes, and records
the original simulation producer separately. `correction-preservation-01/` reseals
both the original preservation baseline and every pre-correction evidence/capture
file plus the original provider generation. All original captures, receipts,
failed attempts, simulation evidence and original final seal remain retained.
Reseal result: original **141450 files /1678 symlinks** and additional correction
baseline **5518 files /2 symlinks**, **zero changes**.

## Original simulation-producing provider provenance (unchanged)

- Generation: `.dev/asic-pt8-workloads/provider/generations/59aeb673765d4ef5b9308eb611f8cf0f`.
- Captured provider snapshot SHA256:
  `4388f670af5951b165b553543d472146b8a77ee350b7ac1a48a5e7e82a8f7e6d`.
- Provider receipt SHA256:
  `16b4c0ed1c1b95f73eb130383e023a0995f51c54ee2c6d2b4caa62ac747c8bd2`.
- Exact source tree and per-file hashes:
  `acceptance/pt8-workloads/capture-02-nested/source-snapshot{,.json}`.
- Seven nested build/install/query/probe receipts are retained there. Capture
  checked B's new `?left_workload` / `?right_workload` interface before starting.
  The wrapper excludes `_build*` source entries and supplies the isolated build
  name to every nested Dune invocation. It changes no shared capture helper.
- Original compiled adapters: `workloads/workload_emit.ml` and
  `workloads/workload_public.ml`, built in `build-02` against that generation.
  The original `final-receipt.json` records exact executable/source hashes, installed CLI and
  native comparison helper hashes, model hashes, commands and evidence inventory.

This is captured local provenance, not authenticated execution or P6 attribution.
The initial construction bootstrap used the retained historical generation
`f205e0d66f8d4f2b8d1e5f098171bb21`; final `simulation-04` was emitted by the freshly
rebuilt adapter against the new provider. Earlier attempts are retained as history.

## Actual matched hardware and execution

`workloads/workload_emit.ml` uses `Project.of_variant`, the unchanged public checked
`Variant_memory.variant 256`, and the unchanged `Variant_memory.core` constructor.
The checked assignment reaches the real `Single_port_ram.Config`: 256×16, one 1RW
port, latency one. The `program` instance has an explicit **Flops** or **Exact**
requirement and no fallback. Both bundles use the same adapter and source closure.

The direct TT-pin adapter avoids extra staging edges: `ui_in` is the eight-bit
address, `uio_in` the low write-data byte, and the high write-data byte equals the
address. `ena` enables the operation; **`rst_n` is an active-low write command,
not a RAM reset** in this specimen. `uo_out` / `uio_out` expose the full sixteen-bit
registered response. This deliberately restricted write-data interface still
exercises all data bits and unique words throughout the complete address space;
it is not an arbitrary-16-bit-data pin protocol. RAM is never initialized/reset.

The harness compiles **bundle `synthesis_sources` implementation RTL**, not
`simulation_sources` or a Cyclesim lowering. Exact instantiates the stock
`RM_IHPSG13_1P_256x16_c2_bm_bist`, executing both stock vendor files:

- `RM_IHPSG13_1P_256x16_c2_bm_bist.v`
- `RM_IHPSG13_1P_core_behavioral_bm_bist.v`

They are copied unchanged from the selected PDK model directory, checked against
the bundle's `implementation_simulation.models`, and compiled with `-DFUNCTIONAL`.
The Flops model-role artifact explicitly declares that no external primitive model
is used. Tool settings bytes are identical across the pair; actual model/RTL bytes
remain distinct provenance. Icarus and vvp executable hashes/versions, complete
compile/execution commands, raw stdout/stderr and the actual testbench are retained.

The testbench settles inputs with clock low, samples before the rising edge, and
samples after nonblocking updates. Its artificial functional clock is 10 ns
(samples at 4/9 ns, rising edge at 5 ns). Both bundles declare a 20 ns implementation
constraint; neither functional driver period nor constraint is a measured Fmax or
a timed-model result. No clock-projected physical speed is claimed.

## Workload and public results

Authoritative passing executions: `simulation-04/{flops,exact}/`. Each retains raw
trace, exact stimulus, independent expected oracle, checked counters, testbench,
source/model/tool artifacts and a unique bundle/variant-bound attempt in **A wire v1**.

The same logical workload identity is
`d647a2c4bd126b9e1e5891b3284bbb5fcb03f19f6c25d9fc2c09bf1d08fac74e`.
It reads undefined initial storage, attempts disabled writes before initialization,
writes all 256 addresses, performs permuted full reads with disabled writes/holds,
reads every address in reverse, and rewrites/readbacks boundaries 0/127/128/255.
Null oracle positions preserve undefined initial and write responses; observed
values there are retained without being asserted equal or sanitized into success.

Original `acceptance-04/assertions.json` and `matched.json` record installed verification and
entire API/CLI response parity. Both variants give:

| Derived metric | Each implementation |
|---|---:|
| Cycles / half-open window | 1307 / [0,1307) |
| Accepted reads | 525 |
| Accepted writes | 262 |
| Accepted operations | 787 |
| Defined before+after observations | 2083 |
| Defined read latency | 1 edge |
| Operation throughput | 787/1307 = 0.6021423106350421 operations/cycle |

All seven workload metrics are **comparable with exactly zero right-minus-left**.
No firmware/fetch metric is invented. Host elapsed time is only a command receipt.

## Semantic, evidence and comparison controls

Two actual intentionally defective simulations complete, remain functional failures
in the installed public reader, and expose no performance values:

- `simulation-04/ignored-workload`: the testbench discards the low data byte;
  **2075** defined observations fail. The logical requested inputs remain in the
  trace, while retained testbench bytes show the intentionally different driving.
- `simulation-04/flops-ignored`: a **separately emitted valid bundle** declares the
  same 256-word hardware but ignores address bit7 in its adapter; **1024** defined
  observations fail. This is a semantic capacity/parameter-use negative, not a
  corrupt hash fixture. The original constructor and all old variants are untouched.

Public verification rejects independently mutated stimulus, trace input, expected
oracle values (including coherently rebound identities), window, all six counters,
workload/bundle/hardware associations, selected bundle, missing/truncated trace,
incomplete completed trace, changed artifact bytes, and coherently rehashed RTL
outside the bundle's selected source set. Public `recheck` passes stable bytes and
rejects changed attempt/source generations. Partial/interrupted/failed **test
fixtures**, derived from real trace prefixes, retain their statuses and withhold
all performance values; they are not claimed as actual interrupted simulations.

`controls-02/assertions.json` adds installed API/CLI parity for wrong-target
association rejection, both semantic-failure comparisons, changed logical workload
and model controls (no comparable delta), and unsupported adapter/clock/measurement
definitions (reader rejection). B owns the provider's exhaustive comparison suite.
Each acceptance query has syscall checks: one API process or same-process native
CLI/helper exec replacement, no child tools/renderers, write-capable file operations
or network operations. Harness writes/copies occur outside those queries.

## Evidence-based tradeoff

**Equal hardware cycle throughput is the expected correct result for this workload.**
Both explicit representations implement the same single-port registered protocol;
the inserted holds and disabled writes are identical. Exact changes storage
structure from the emitted flop storage/decode to one stock macro. That is a real
selection/structure tradeoff and supports evaluating macro availability/integration
versus flop portability; it establishes neither an area saving nor a speed winner.

Accepted retained SRAM physical P4 summary and bundle were inspected read-only:
`acceptance/sram/physical-p4/summary.json`, run
`be961b2c95f74c81ad6af81ca4d2b269`, bundle
`fa38d9064dffdf2ec1578c79c2e8890eba81bf704af460e85fcc6031b707d53c`.
That historical Exact consumer has staging registers, different adapter/clock/flow
settings, and no matched physical Flops counterpart. Its accepted implementation
is qualified feasibility context only. **Area and physical-speed A/B deltas remain
unsupported.** No synthesis/P&R/STA was allocated or run for this workload.

## Preservation, failures and limits

`preservation-baseline.json` records original Git status/diff and hashes of modified,
untracked and retained historical regular files/symlinks, including ignored stores
and tool collateral. `preservation-final.json` rechecks **141450 files and 1678
symlinks, zero changes**, including existing `acceptance/dune`, `asic/project.ml`,
old variants, historical providers and evidence. Build caches, Git internals and
the new owned scope are explicitly excluded. No Git mutation, provider selection
outside the new store, application configuration or daemon changes were made.

Retained construction/capture/harness failures:

- Initial terminal builds: missing public shim source, then old switch lacking
  Hardware_variant; bootstrap explicitly selected the retained installed generation.
- Initial core-port emission failed TT pin validation; the new direct TT adapter
  fixed that boundary without altering `variants/`.
- `simulation-01`: Python tuple unpacking error while preparing the defective RTL
  fixture. `simulation-02`: defective fixture's port-header name mismatch rejected
  by Icarus. `simulation-03` passes its original four simulations; its mutated-RTL
  hardware fixture is superseded by the valid emitted negative in `simulation-04`.
- `capture-01`: concurrent provider build products entered source selection and
  caused a broken-source-symlink capture error. `capture-02` excludes build products.
- `acceptance-01..03`: harness expected different diagnostic wording / comparison
  JSON field names. Public errors/responses are retained; `acceptance-04` passes.
- `controls-01`: harness initially expected changed adapter semantics to be readable;
  A's strict supported-protocol gate correctly rejects. `controls-02` passes.

Across all attempts **12 vvp processes actually executed**, sequentially, including
superseded positives and intentional negatives. Icarus compile failures are separate
retained commands. EDA allocation/use is zero. Build/capture uses switch5.2.0+ox,
explicit six-job Dune and the shared example/ASIC locks (nested capture serialized).
No functional simulator skip occurred.

A's supported bounds: 1..4096 operations; result/stimulus/trace/simulation each
1 MiB; at most32 artifacts, 8 MiB each /32 MiB combined; projection1 MiB; fixed
256×16 protocol. These are provider limits, not newly claimed boundary coverage by
C. Query deadlines are180s, capture1800s. Timed SRAM/SDF, exhaustive equivalence,
authentication and Protemu adoption remain outside this evidence.

## Read-only reproduction / independent review handoff

From the example root, use fresh attempt names (existing evidence is never replaced):

```sh
GEN="$PWD/.dev/asic-pt8-workloads/provider/generations/1d3e1195ba4f45fb93eb986ca23cfb75"
python3 -B scripts/pt8_workloads.py build --attempt review-build-NEW --generation "$GEN"
python3 -B scripts/pt8_workloads_acceptance.py --attempt review-acceptance-NEW \
  --simulation simulation-04 --generation "$GEN"
python3 -B scripts/pt8_workloads_controls.py --attempt review-controls-NEW \
  --simulation simulation-04 --generation "$GEN"
python3 -B scripts/pt8_workloads_regressions.py --attempt review-regressions-NEW \
  --generation "$GEN"
```

For read-only verification of the current retained pass, run the public adapter's
`inspect PATH`, `recheck PATH DIGEST`, or `compare LEFT_BUNDLE RIGHT_BUNDLE
LEFT_RESULT RIGHT_RESULT`. Native CLI uses `compare --left-kind bundle --left PATH
--right-kind bundle --right PATH --axis resource_policy --left-workload RESULT
--right-workload RESULT --json`. Exact executed commands are in the passing receipts.
Review should particularly inspect direct pin/data constraints, undefined-output
positions, actual stock-model execution, ignored-address semantic failure and
the honest absence of matched physical area/speed evidence.
