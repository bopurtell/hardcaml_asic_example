open! Core
open Hardcaml
open Hardcaml_asic

module I = struct
  type 'a t =
    { clock : 'a; enable : 'a; write_enable : 'a
    ; address : 'a [@bits 8]; write_data : 'a [@bits 16] }
  [@@deriving hardcaml]
end

module O = struct
  type 'a t = { read_data : 'a [@bits 16] } [@@deriving hardcaml]
end

let schema =
  let parameter key minimum maximum =
    Hardware_variant.Parameter.create ~key ~kind:(Integer { minimum; maximum })
    |> Or_error.ok_exn
  in
  Hardware_variant.Schema.create ~design_id:"pt8_memory" ~schema_id:"pt8_memory.v1"
    ~parameters:[ parameter "depth" 128 256; parameter "width" 16 16
                ; parameter "read_latency" 1 1 ]
  |> Or_error.ok_exn
;;

let variant depth =
  Hardware_variant.create ~schema
    ~assignments:[ "depth", Int depth; "width", Int 16; "read_latency", Int 1 ]
;;

let shape checked =
  let open Or_error.Let_syntax in
  let%bind depth = Hardware_variant.get_int checked ~key:"depth" in
  let%bind width = Hardware_variant.get_int checked ~key:"width" in
  let%bind read_latency = Hardware_variant.get_int checked ~key:"read_latency" in
  let%bind expected = variant depth in
  if not (String.equal (Hardware_variant.Schema.design_id (Hardware_variant.schema checked)) "pt8_memory")
     || not (String.equal (Hardware_variant.Schema.schema_id (Hardware_variant.schema checked)) "pt8_memory.v1")
     || not (String.equal (Hardware_variant.identity checked) (Hardware_variant.identity expected))
     || not (List.mem [128; 256] depth ~equal:Int.equal) || width <> 16 || read_latency <> 1
  then Or_error.error_string "Unsupported PT8 memory tuple"
  else Ok (depth, width, read_latency)
;;

(* The checked assignment, not a separately supplied depth, reaches the real RAM.
   [ignore_depth] is deliberately defective and is exposed only for the negative. *)
let core ~ignore_depth checked context (i : _ I.t) =
  let depth, width, read_latency = shape checked |> Or_error.ok_exn in
  let depth = if ignore_depth then 256 else depth in
  let address = if depth = 128 then Signal.select i.address ~high:6 ~low:0 else i.address in
  { O.read_data =
      Single_port_ram.create context ~name:"program"
        (Single_port_ram.Config.create_exn ~width ~depth ~read_latency)
        ~clock:i.clock ~enable:i.enable ~write_enable:i.write_enable
        ~address ~write_data:i.write_data }
;;

let tt ~ignore_depth checked context (i : _ Tt_cmos5l.I.t) =
  let open Signal in
  let active = i.ena &: i.rst_n in
  let command = select i.ui_in ~high:1 ~low:0 in
  let spec = Reg_spec.create ~clock:i.clk ~clear:(~:(i.rst_n)) () in
  let address = reg spec ~enable:(active &: (command ==:. 1)) i.uio_in in
  let low_data = reg spec ~enable:(active &: (command ==:. 2)) i.uio_in in
  let memory = core ~ignore_depth checked context
      { clock = i.clk; enable = active &: ((command ==:. 0) |: (command ==:. 3))
      ; write_enable = command ==:. 3; address
      ; write_data = concat_msb [ i.uio_in; low_data ] } in
  { Tt_cmos5l.O.uo_out = Tt_cmos5l.gate ~enable:active
      (mux2 (bit i.ui_in ~pos:2)
         (select memory.read_data ~high:15 ~low:8)
         (select memory.read_data ~high:7 ~low:0))
  ; uio_out = zero 8; uio_oe = zero 8 }
;;

let source_inputs =
  [ "dune-project"; "tooling_acceptance/variants/dune"
  ; "tooling_acceptance/variants/variant_memory.ml"
  ; "tooling_acceptance/variants/variant_cli.ml"
  ; "tooling_acceptance/variants/README.md"
  ; "asics/fifo_demo/project/flow_profiles.ml"
  ; "asics/fifo_demo/project/flow_catalog.ml" ]
;;

let project ?(core_ports = false) ?(ignore_depth = false) checked requirement =
  Project.of_variant ~variant:checked ~create:(fun checked ->
    let open Or_error.Let_syntax in
    let%bind _ = shape checked in
    let%bind policy = Resource_policy.create
        [ { selector = Resource_policy.Selector.instance_exn "program"; requirement } ] in
    let design =
      if core_ports then
        let module D = struct
          module I = I
          module O = O
          let name = "pt8_memory_core"
          let create = core ~ignore_depth checked
        end in (module D : Project.Design)
      else
        let module D = struct
          module I = Tt_cmos5l.I
          module O = Tt_cmos5l.O
          let name = "tt_um_pt8_memory"
          let create = tt ~ignore_depth checked
        end in (module D : Project.Design)
    in
    Project.create ~name:"pt8_memory" ~source_inputs
      ~metadata:{ title = "PT8 memory"; author = "hardcaml_asic_example"
                ; description = "Checked depth128/256 width16 latency1 memory" }
      ~design
      ~target:{ harness = Tiny_tapeout { tiles = T6x4 }; technology = Technology.ihp_sg13cmos5l }
      ~flow:(Flow.librelane Synthesis)
      ~clocks:[ { Clock.port = "clk"; period = Time_float.Span.of_ns 20. } ]
      ~pinout:(List.concat_map [ Pinout.Bank.Ui; Uo; Uio ] ~f:(fun bank ->
        List.init 8 ~f:(fun bit ->
          let description = match bank with
            | Ui -> (match bit with
                | 0 | 1 -> sprintf "Command bit %d: read/address/low-data/commit" bit
                | 2 -> "Response byte select" | _ -> "Unused command input")
            | Uo -> sprintf "Registered response byte bit %d" bit
            | Uio -> sprintf "Address/write-data byte input bit %d" bit in
          { Pinout.bank; bit; description })))
      ~policy ())
;;
