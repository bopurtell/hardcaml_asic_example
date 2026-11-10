open! Core
open Hardcaml
open Hardcaml_asic

let stages =
  List.concat_map
    [ "capture", [ "capture_first"; "capture_second"; "capture_third" ]
    ; "control", [ "control_first"; "control_second" ]
    ]
    ~f:(fun (chain, ids) ->
      List.mapi ids ~f:(fun index id -> Timing.Stage.create ~id ~chain ~index))
;;

module Design = struct
  module I = Tt_cmos5l.I
  module O = Tt_cmos5l.O

  let name = "tt_um_pt7_timing"

  let create context (i : _ I.t) =
    let open Signal in
    let anchor id q =
      let stage = List.find_exn stages ~f:(fun stage -> String.equal stage.id id) in
      Elaboration.Context.register_timing_stage_exn context ~stage ~q;
      q
    in
    let o = Timing_specimen.create ~anchor
      { clk = i.clk; rst_n = i.rst_n; asynchronous = i.ena; synchronous = bit i.ui_in ~pos:1 }
    in
    let gate = bit i.ui_in ~pos:2 in
    { O.uo_out = concat_msb [ zero 6; o.control &: gate; o.captured &: gate ]
    ; uio_out = zero 8
    ; uio_oe = zero 8
    }
  ;;
end

let source_inputs =
  [ "dune-project"; "asic-dependency.json"
  ; "tooling_acceptance/timing/fixture/timing_specimen.ml"
  ; "tooling_acceptance/timing/fixture/timing_specimen.mli"
  ; "tooling_acceptance/timing/physical/dune"
  ; "tooling_acceptance/timing/physical/physical_project.ml"
  ; "tooling_acceptance/timing/physical/physical_timing_cli.ml"
  ]
;;

let create ~full =
  let open Or_error.Let_syntax in
  let%bind policy = Resource_policy.create ~default:Flops [] in
  let delays ports maximum =
    List.map ports ~f:(fun port ->
      { Timing.Delay.port; minimum = Time_float.Span.of_ns 0.
      ; maximum = Time_float.Span.of_ns maximum })
  in
  Project.create
    ~name:"timing_physical_specimen"
    ~source_inputs
    ~metadata:
      { title = "Independent physical timing qualification"
      ; author = "hardcaml_asic_example"
      ; description = "Five original stages; physical timing evidence, no CDC or reset-protocol approval"
      }
    ~design:(module Design)
    ~target:{ harness = Tiny_tapeout { tiles = T6x4 }; technology = Technology.ihp_sg13cmos5l }
    ~flow:(Flow.librelane ~overrides:(Tt_cmos5l.overrides ()) (if full then Hardening else Synthesis))
    ~clocks:[ { Clock.port = "clk"; period = Time_float.Span.of_ns 20. } ]
    ~pinout:
      (List.concat_map [ Pinout.Bank.Ui; Uo; Uio ] ~f:(fun bank ->
         List.init 8 ~f:(fun bit ->
           let description =
             match bank, bit with
             | Ui, 1 -> "Synchronous control specimen input"
             | Ui, 2 -> "Output gate; scalar ena is the asynchronous capture source"
             | Uo, 0 -> "Third capture stage, gated output"
             | Uo, 1 -> "Second control stage, gated output"
             | Ui, _ | Uio, _ -> "Unused input; no active bidirectional outputs"
             | Uo, _ -> "Constant zero output"
           in
           { Pinout.bank; bit; description })))
    ~timing:
      (Timing.create
         ~input_delays:(delays [ "ui_in"; "uio_in"; "ena"; "rst_n" ] 1.)
         ~output_delays:(delays [ "uo_out"; "uio_out"; "uio_oe" ] 2.)
         ~stages
         ~exceptions:
           [ Timing.Exception.async_capture ~id:"external_capture"
               ~reason:"Independent asynchronous specimen input: waive only the first data pin"
               ~source:(Timing.Port.input "ena") ~first_stage:(List.hd_exn stages)
           ; Timing.Exception.async_reset ~id:"external_reset"
               ~reason:"External active-low reset: enumerated asynchronous controls; protocol review pending"
               ~source:(Timing.Port.input "rst_n") ~targets:stages
           ]
         ())
    ~policy ()
;;
