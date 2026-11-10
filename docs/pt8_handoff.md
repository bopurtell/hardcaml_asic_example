# C PT8 handoff / coordination

> **Historical execution paths:** active variant/workload source now lives under
> `tooling_acceptance/`. See the [layout map](repository_layout.md); retained
> execution identities and evidence paths below remain unchanged.

2026-10-29. Preparation is complete in C-owned paths. Read
`docs/pt8_acceptance.md` and `variants/README.md` for the adapter/oracle contract.
Pre-capture preservation: 108,338 files and 65 symlinks unchanged.

A's validation handoff is available (85 schema + 41 integration checks,
historical absence and install build). B's qualification handoff was read before
the isolated installed provider capture. C acceptance is now complete; see
`pt8_final.md` and `acceptance/pt8/matrix-03/assertions.json` (204 assertions).

Planned exact real targets:

- Named area:
  `.dev/asic-pt7named/workspaces/area-run-final-04/execution-cb5e7cd92dbf43b4a6c00a74b61c6d72.json`
- Named delay:
  `.dev/asic-pt7named/workspaces/delay-run-final-03/execution-9374823306a64897959e1b2295f52c84.json`
- Accepted physical:
  `.dev/asic-timing-physical/full-runs/20261029T075052976305Z_23a6954b`

Consumer harness contains no production evidence parser/comparison implementation.
The API shim calls Variant_comparison.inspect and the matrix compares its entire
JSON to the installed native CLI. All invocations trace writes/process launches.

Review note for B: ensure real physical self-comparison fits the 1MiB complete
response bound when retaining sources per metric (do not silently truncate).
Authoritative whole-design native metrics are useful where available; missing
historical hardware parameters must remain unavailable even for equal netlists.

## Installed findings (first capture)

Provider `d36e6cd31c894dc384e7757716bb87ee` captured after both readiness handoffs.
Five positive and one deliberate ignored-depth simulations have run; positives
pass, negative independently fails actual request and address128 alias behavior.
Do not allocate additional functional simulation runs.

Retained failures: first emission lacked TT pin descriptions (C fixed); source
evidence copies were initially discovered by Dune (C isolated evidence with dirs).
Exact256 via `Methodology_plan.prepare` returns
`Invalid_argument "object fields do not match versioned schema"` even though
Exact256 functional selection passes. In `lib/methodology_plan.ml`,
`verify_associations`' manifest whitelist does not admit macro_contract fields;
configuration/generated-source validation also assumes a single nonmacro Verilog
file. A owns that code. No production workaround/parser is added by C.

For the requested new bundle comparisons C uses the existing uniform public
`Flow.Catalog.resolve` -> `Project.render_result ~methodology ~catalog_inputs` ->
`Bundle.publish` path for **all** new bundles, preserving actual existing profile
assignments and one-render publication for both Flops and Exact. This does not
claim new Exact methodology-plan support. Failed preparations remain retained in
`acceptance/pt8/emit-02` and `emit-03`.
