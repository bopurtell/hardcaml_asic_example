# Corrected-provider round r2

**Blocked by a newly reproduced native source-net API issue, A-REAL-2.**
Both fresh bit/scalar bundles emitted and mapped successfully; both unmodified
SDCs failed native STA before validation/application. Prior scalar acceptance
belongs to its original provider and is not corrected-provider acceptance.

See `../../docs/pt7_timing_corrected.md` and `../../docs/pt7_timing_findings.md`.
New raw attempts are `capture-02`, `emitter-build-05/06`, `emission-*-r2`,
`synth-*-r2*`, `sta-*-r2*`, `port-net-probe-r2*`, `port-net-openroad-r2*`.
`connectivity-bit-r2-prepared` is preparation, not passing native evidence.
`closeout-r2` retains exact identities, failure assertions and checksums.
