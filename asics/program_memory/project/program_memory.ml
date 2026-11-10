open! Core
open Hardcaml
open Hardcaml_asic

module I = struct
  type 'a t =
    { clock : 'a
    ; enable : 'a
    ; write_enable : 'a
    ; address : 'a [@bits 8]
    ; write_data : 'a [@bits 16]
    }
  [@@deriving hardcaml]
end

module O = struct
  type 'a t = { read_data : 'a [@bits 16] } [@@deriving hardcaml]
end

let config = Single_port_ram.Config.create_exn ~width:16 ~depth:256 ~read_latency:1

let create_with_depth depth context (i : _ I.t) =
  let config = Single_port_ram.Config.create_exn ~width:16 ~depth ~read_latency:1 in
  { O.read_data =
      Single_port_ram.create context ~name:"program" config
        ~clock:i.clock ~enable:i.enable ~write_enable:i.write_enable
        ~address:(if depth = 256 then i.address else Signal.select i.address ~high:6 ~low:0)
        ~write_data:i.write_data
  }
;;

let create = create_with_depth 256

(* A byte-wide TT adapter keeps the complete 256x16 core accessible. Commands
   stage address and low data separately; only read/commit touch the memory. *)
module Tt = struct
  module I = Tt_cmos5l.I
  module O = Tt_cmos5l.O

  let name = "tt_um_program_memory"

  let create_with_depth depth context (i : _ I.t) =
    let open Signal in
    let active = i.ena &: i.rst_n in
    let command = select i.ui_in ~high:1 ~low:0 in
    let spec = Reg_spec.create ~clock:i.clk ~clear:(~:(i.rst_n)) () in
    let address = reg spec ~enable:(active &: (command ==:. 1)) i.uio_in in
    let low_data = reg spec ~enable:(active &: (command ==:. 2)) i.uio_in in
    let memory =
      create_with_depth depth context
        { clock = i.clk
        ; enable = active &: ((command ==:. 0) |: (command ==:. 3))
        ; write_enable = command ==:. 3
        ; address
        ; write_data = concat_msb [ i.uio_in; low_data ]
        }
    in
    let byte =
      mux2 (bit i.ui_in ~pos:2)
        (select memory.read_data ~high:15 ~low:8)
        (select memory.read_data ~high:7 ~low:0)
    in
    { O.uo_out = Tt_cmos5l.gate ~enable:active byte
    ; uio_out = zero 8
    ; uio_oe = zero 8
    }
  ;;
  let create = create_with_depth 256
end

let source_inputs =
  [ "dune-project"; "asic-dependency.json"; "asics/program_memory/project/dune"
  ; "asics/program_memory/project/program_memory.ml"; "asics/program_memory/project/memory_cli.ml"; "asics/program_memory/README.md"
  ]
;;

(* No default or fallback: a misspelled identity fails policy finalization. *)
let policy requirement =
  Resource_policy.create
    [ { selector = Resource_policy.Selector.instance_exn "program"; requirement } ]
;;

(* Keep existing OCaml callers' operation defaults. The CLI always supplies one. *)
let project ?(with_macro_intent = true) ?(depth = 256) ?operation requirement =
  let open Or_error.Let_syntax in
  let%bind policy = policy requirement in
  let operation =
    Option.value operation ~default:(
      match requirement with
      | Resource_policy.Requirement.Exact -> Flow.Operation.Synthesis
      | _ -> Flow.Operation.Hardening)
  in
  let macros =
    match requirement with
    | Resource_policy.Requirement.Exact when with_macro_intent ->
      (* Hardening candidate: align the selected positive M4 fingers more fully
         with the grid. Actual power access is the provider's execution check. *)
      let x_um = match operation with Flow.Operation.Synthesis -> 42. | Hardening -> 40. in
      [ Macro_intent.tt_cmos5l_r0 ~resource:(Resource.Id.of_string_exn "program")
          ~x_um ~y_um:81. ~halo_um:2. () ]
    | _ -> []
  in
  let overrides =
    match requirement, operation with
    | Resource_policy.Requirement.Exact, Flow.Operation.Hardening ->
      (* The physical provider generates these facts, including deprecated PDN
         aliases. Keep the complete template defaults on every other path. *)
      Tt_cmos5l.overrides
        ~without:[ "RUN_KLAYOUT_DRC"; "FP_PDN_VPITCH"; "FP_PDN_VWIDTH"; "FP_PDN_MULTILAYER" ] ()
    | _ -> Tt_cmos5l.overrides ()
  in
  let delays ports maximum =
    List.map ports ~f:(fun port ->
      { Timing.Delay.port
      ; minimum = Time_float.Span.of_ns 0.
      ; maximum = Time_float.Span.of_ns maximum
      })
  in
  let module Design = struct
    include Tt
    let create = Tt.create_with_depth depth
  end in
  Project.create ~source_inputs ~name:"program_memory_specimen"
    ~metadata:
      { title = "Program memory"; author = "hardcaml_asic_example"
      ; description = "Registered 256x16 1RW latency-one memory consumer"
      }
    ~design:(module Design)
    ~target:{ harness = Tiny_tapeout { tiles = T6x4 }; technology = Technology.ihp_sg13cmos5l }
    ~flow:(Flow.librelane ~overrides ~macros operation)
    ~clocks:[ { Clock.port = "clk"; period = Time_float.Span.of_sec (1. /. 48e6) } ]
    ~timing:
      (Timing.create
         ~input_delays:(delays [ "ui_in"; "uio_in"; "ena"; "rst_n" ] 1.)
         ~output_delays:(delays [ "uo_out"; "uio_out"; "uio_oe" ] 2.)
         ())
    ~pinout:
      (List.concat_map [ Pinout.Bank.Ui; Uo; Uio ] ~f:(fun bank ->
         List.init 8 ~f:(fun bit ->
           let description =
             match bank with
             | Ui ->
               (match bit with
                | 0 | 1 -> sprintf "Command bit %d: read/address/low-data/commit" bit
                | 2 -> "Response byte select: 0 low, 1 high"
                | _ -> "Ignored input")
             | Uo -> sprintf "Selected registered response byte bit %d" bit
             | Uio -> sprintf "Address or write-data byte bit %d; input only" bit
           in
           { Pinout.bank; bit; description })))
    ~policy ()
;;
