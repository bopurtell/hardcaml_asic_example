let source_inputs =
  Fifo_flows.Generated.source_inputs @
  ["asics/fifo_demo/project/flow_catalog.ml"; "asics/fifo_demo/project/flow_catalog.mli"]

let create () =
  Fifo_flows.Generated.create ~default_flow:"standard" ~default_profile:"balanced"
