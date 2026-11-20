# Three memory banks sharing an SRAM budget

Each bank requests the same 256×16 single-port RAM. The project gives all three
the same requirement and caps the number of instances of the stock IHP SRAM:

```ocaml
Resource_policy.create ~default:Exact_or_flop_fallback ~macro_limits:[ stock_macro, budget ] []
```

The banks register in order. With two slots, `bank0` and `bank1` receive the
macro; `bank2` falls back to flops because the budget is exhausted. With
three slots, `bank2` also receives the macro. In both cases it requested the
same implementation policy. The slot count is a project limit, not a PDK
inventory limit.

The shared [project CLI](../../README.md#project-cli) registers `two_slot`
and `three_slot` under `sram_budget`, with `standard` / `balanced` and one
named endpoint, `synthesis`. The selected variant appears as `bank_variant`
in the bundle's hardware declaration. In particular, a two-slot plan cannot
authorize the emission or execution of a three-slot bundle. For durable
elaboration evidence only, use `project prepare --chip sram_budget --variant
three_slot --json`. Both `flow plan` and `flow emit` are EDA-free.

With a `hardcaml_asic` build that exposes `Resource_policy.create ~macro_limits`,
run these commands from `hardcaml_asic_example` using new or empty output directories:

```sh
dune exec asics/sram_budget/emit.exe -- 2 "$PWD" "$PWD/_flow_results/sram-budget-2"
dune exec asics/sram_budget/emit.exe -- 3 "$PWD" "$PWD/_flow_results/sram-budget-3"
```

In Silver use **Resources: Import emitted bundle** and paste the absolute
two-slot output directory. Capture it as A, then import the three-slot directory
and capture it as B. These bundles show elaboration;
synthesis and final observations are unavailable until there is run evidence.

`dune runtest asics/sram_budget` emits fresh bundles for both budgets, checks
each bank through the provider's resource inspector, and matches its instance
names against the generated Verilog. The test needs no PDK or synthesis tools.
If `iverilog` and `vvp` are available, it also replays a bank-isolation test on
each bundle's behavioral Verilog.

### Using the sibling provider checkout

When the installed switch predates macro limits, build and test against
`../hardcaml_asic` instead. The helper uses a private `_build_asic_dev` directory:

```sh
./scripts/build_with_asic_checkout.sh @asics/sram_budget/runtest
_build_asic_dev/default/asics/sram_budget/emit.exe 2 "$PWD" "$PWD/_flow_results/sram-budget-dev-2"
_build_asic_dev/default/asics/sram_budget/emit.exe 3 "$PWD" "$PWD/_flow_results/sram-budget-dev-3"
```

Start a fresh Silver daemon with the matching provider so the inspector
understands the budget-exhaustion reason:

```sh
SILVER_ASIC_PROVIDER="$PWD/../hardcaml_asic/_build/install/default/bin/hardcaml-asic-flow" silver
```

If the project pins an absolute `provider_executable`, point that setting at
the same provider; a pin takes precedence over discovery.
