# Latest PT.7 result: final candidate r3

**Actual bounded bit and scalar native acceptance completed; native coverage
remains intentionally unavailable (B CLI exit 1).**

Full report: `../../docs/pt7_timing_final.md`.

* Provider capture/build: `capture-03/`, `emitter-build-07/`.
* Fresh public bundles: `synth-bit-r3-bundle/`, `synth-scalar-r3-bundle/`.
* Actual mapped products: `synth-bit-r3/`, `synth-scalar-r3/`.
* Native audits: `sta-bit-r3/`, `sta-scalar-r3/`.
* B CLI/report assertions: `checked-bit-r3/`, `checked-scalar-r3/`.
* Graph/buffer fixtures: `connectivity-bit-r3/`, `connectivity-scalar-r3/`.
* Q/source output-tap controls: `taps-bit-r3/`, `taps-scalar-r3/`.
* Anchor/scope negatives: `negative-*-r3*`, `native-negatives-summary-r3.json`.
* Native unconstrained diagnostic: `native-unconstrained-r3*`.
* B semantic suites: `semantic-bit-r3/`, `semantic-scalar-r3/`,
  `semantic-envelope-bit-r3/`.
* Final identities/preservation/checksums: `closeout-final-r3/`.

All earlier failures and closeouts remain immutable historical attempts. This
index supersedes their historical status text; it does not rewrite their bytes.
Three downstream hold samples per main audit remain violated at −0.044244 ns;
timing closure, exhaustive native coverage and P&R are not claimed.
