# PT.7 timing evidence

Current status: **scalar-source real synthesis/STA acceptance executed, native
coverage unavailable; bit-source lookup bug open in captured provider**. See
`../../docs/pt7_timing_acceptance.md` for exact commands, identities, assertions,
failures and limitations, and `../../docs/pt7_timing_findings.md` for A-REAL-1.

`preparation/core-02/receipt.json` records passing provider-independent core
checks. `core-01/` retains the failed first test. Version-only tool launch receipts
are not linked STA or synthesis evidence. The completed provider was subsequently
captured in the isolated PT.7 child store.

Each resumed build/audit must use a new directory and bind exact bundle, producer,
inputs and reports according to B's public timing-evidence contract.

Current evidence:

* `synth-scalar-01-bundle/`: full fresh public emission.
* `synth-scalar-01/`: Yosys script/inputs, mapped Verilog/JSON and inventory.
* `sta-scalar-02/`: B schema-1 audit, receipt, exact inputs and native reports.
* `checked-scalar-02/`: assertions, public CLI exit 1/unavailable, seven rejected
  evidence fixtures (exit 2).
* `negative-*-02*`: five native fail-before-application fixtures (exit 1).
* `native-unconstrained-02*`: intentionally unconstrained diagnostic control.
* `closeout-01/`: producer/source identities and all-evidence checksums.

`sta-01/` retains the failed bit-source audit, not a successful timing result.
