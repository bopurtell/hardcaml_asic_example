open! Core
open Hardcaml_asic

let create () =
  let open Or_error.Let_syntax in
  let profile id label description strategy =
    Flow.Profile.create ~id ~label ~description
      ~assignments:
        [ Flow.Parameter.synth_strategy strategy
        ; Flow.Parameter.synth_abc_buffering false
        ]
  in
  let%bind balanced = profile "balanced" "Balanced" "Explicit area-oriented synthesis baseline" Area_0 in
  let%map synth_delay = profile "synth_delay" "Synthesis delay" "Delay-oriented synthesis strategy" Delay_1 in
  [ balanced; synth_delay ]
;;
