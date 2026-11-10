open! Core
open Hardcaml_asic

let source_inputs =
  [ "named_timing/dune"; "named_timing/named_catalog.ml"; "named_timing/named_timing_cli.ml" ]
;;

let create () =
  let open Or_error.Let_syntax in
  let%bind methodology =
    Flow.Methodology.create ~id:"timing_synthesis" ~label:"Timing synthesis"
      ~description:"Fresh macro-free synthesis with retained native timing evidence"
      ~backend_recipe:Librelane_classic_v1 ~endpoints:[ Flow.Stage.Synthesis ]
      ~configurable:Flow.Parameter.Key.all ~defaults:[]
  in
  let profile id strategy =
    Flow.Profile.create ~id ~label:id ~description:("Explicit synthesis profile " ^ id)
      ~assignments:
        [ Flow.Parameter.synth_strategy strategy
        ; Flow.Parameter.synth_abc_buffering false
        ]
  in
  let%bind area = profile "area" Area_0 in
  let%bind delay = profile "delay" Delay_1 in
  let%bind entry =
    Flow.Catalog.Entry.create ~methodology ~profiles:[ area; delay ] ~default_profile:"area"
  in
  Flow.Catalog.create ~entries:[ entry ] ~default_flow:"timing_synthesis" ~default_profile:"area"
;;
