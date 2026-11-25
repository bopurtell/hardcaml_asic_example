# Program-memory physical verification

The example declares a stock 256×16 SRAM with explicit placement and power intent.
The physical verification harness consumes an actual provider run; it does not
perform hardening itself or substitute synthetic evidence for physical checks.

Use a compatible installed provider and a fresh run directory. From the checkout
root, the following commands describe the available inputs and outputs:

```sh
python3 asics/program_memory/physical/check_physical.py --help
python3 asics/program_memory/physical/complete_physical.py --help
python3 asics/program_memory/physical/package_physical.py --help
python3 asics/program_memory/physical/verify_evidence.py --help
python3 asics/program_memory/verif/replay_snapshot.py --help
```

`check_physical.py` checks actual bundle, run and provider-generation inputs.
`complete_physical.py` completes a portable evidence snapshot; `package_physical.py`
archives it and verifies restored checksums and positive/negative gate replay.
The physical contract and record validators are shared with the bundle checks.
These checks do not establish timed SRAM behavior, internal-device LVS, or IR/EM.

Historical physical runs, including failures, and their original documentation
are preserved outside the public checkout in the development archive.
