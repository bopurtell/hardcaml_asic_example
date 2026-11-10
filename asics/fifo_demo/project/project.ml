open! Core
open Hardcaml_asic

module Design = struct
  include Tt_wrapper

  let create _context = Tt_wrapper.create
end

let pinout : Pinout.t =
  List.concat_map [ Pinout.Bank.Ui; Uo; Uio ] ~f:(fun bank ->
    List.init 8 ~f:(fun bit ->
      let description =
        match bank with
        | Ui -> sprintf "Push data bit %d (bit 0 LSB)" bit
        | Uo -> sprintf "Registered pop response bit %d; masked when disabled/reset" bit
        | Uio ->
          (match bit with
           | 0 -> "Push request input; output disabled"
           | 1 -> "Pop request input; output disabled"
           | 2 -> "Registered response valid output; input ignored"
           | _ -> sprintf "Occupancy bit %d output (pin 3 LSB); input ignored" (bit - 3))
      in
      { Pinout.bank; bit; description }))
;;

let source_inputs =
  Flow_catalog.source_inputs @ [ "dune-project"
  ; "asic-dependency.json"
  ; "README.md"
  ; "ip/controlled_fifo/rtl/dune"
  ; "ip/controlled_fifo/rtl/controlled_fifo.ml"
  ; "ip/controlled_fifo/rtl/controlled_fifo.mli"
  ; "asics/fifo_demo/project/dune"
  ; "asics/fifo_demo/rtl/tt_wrapper.ml"
  ; "asics/fifo_demo/rtl/tt_wrapper.mli"
  ; "asics/fifo_demo/project/project.ml"
  ; "asics/fifo_demo/project/project.mli"
  ; "asics/fifo_demo/project/fifo_asic.ml"
  ; "asics/fifo_demo/project/fifo_asic.mli"
  ; "asics/fifo_demo/cli/dune"
  ; "asics/fifo_demo/cli/project.ml"
  ]
;;

let create () =
  let open Or_error.Let_syntax in
  (* Ordinary core registers do not register Single_port_ram resources. *)
  let%bind policy = Resource_policy.create ~default:Flops [] in
  let delays ports maximum =
    List.map ports ~f:(fun port ->
      { Timing.Delay.port
      ; minimum = Time_float.Span.of_ns 0.
      ; maximum = Time_float.Span.of_ns maximum
      })
  in
  Hardcaml_asic.Project.create
    ~source_inputs
    ~name:"controlled_fifo_specimen"
    ~metadata:
      { title = "Controlled FIFO"
      ; author = "hardcaml_asic_example"
      ; description = "16x8 register-backed FIFO with registered pop responses"
      }
    ~design:(module Design)
    ~target:
      { harness = Tiny_tapeout { tiles = T6x4 }
      ; technology = Technology.ihp_sg13cmos5l
      }
    ~flow:(Flow.librelane ~overrides:(Tt_cmos5l.overrides ()) Hardening)
    ~clocks:[ { Clock.port = "clk"; period = Time_float.Span.of_sec (1. /. 48e6) } ]
    (* Specimen analysis budgets, not measured board timing or physical acceptance. *)
    ~timing:
      (* The approved Workbench provider predates [Timing.create]. Updating one
         field at a time also preserves newer optional timing-intent defaults. *)
      (let timing =
         { Timing.empty with
           input_delays = delays [ "ui_in"; "uio_in"; "ena"; "rst_n" ] 1.
         }
       in
       { timing with output_delays = delays [ "uo_out"; "uio_out"; "uio_oe" ] 2. })
    ~pinout
    ~policy
    ()
;;
