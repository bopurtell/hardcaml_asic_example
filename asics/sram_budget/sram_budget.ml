open! Core
open Hardcaml
open Hardcaml_asic

(* Registration order is also the bank decoder order. *)
let banks = [ "bank0"; "bank1"; "bank2" ]
let stock_macro = "RM_IHPSG13_1P_256x16_c2_bm_bist"

module Design = struct
  module I = Tt_cmos5l.I
  module O = Tt_cmos5l.O
  let name = "tt_um_sram_budget"

  let create context (i : _ I.t) =
    let open Signal in
    let active = i.ena &: i.rst_n in
    let cmd = select i.ui_in ~high:1 ~low:0 in
    let bank = select i.ui_in ~high:4 ~low:3 in
    let spec = Reg_spec.create ~clock:i.clk ~clear:(~:(i.rst_n)) () in
    let stage n = reg spec ~enable:(active &: (cmd ==:. n)) i.uio_in in
    let address = stage 1 in
    let write_data = concat_msb [ i.uio_in; stage 2 ] in
    let config = Single_port_ram.Config.create_exn ~width:16 ~depth:256 ~read_latency:1 in
    let responses = List.mapi banks ~f:(fun n name ->
      Single_port_ram.create context ~name config ~clock:i.clk
        ~enable:(active &: (bank ==:. n) &: ((cmd ==:. 0) |: (cmd ==:. 3)))
        ~write_enable:(cmd ==:. 3) ~address ~write_data)
    in
    let word = mux bank (responses @ [ zero 16 ]) in
    let byte = mux2 (bit i.ui_in ~pos:2) (sel_top word ~width:8) (sel_bottom word ~width:8) in
    { O.uo_out = Tt_cmos5l.gate ~enable:active byte; uio_out = zero 8; uio_oe = zero 8 }
  ;;
end

let chip_target ?(extra_inputs = []) ~budget () =
  let policy =
    Resource_policy.create ~default:Exact_or_flop_fallback
      ~macro_limits:[ stock_macro, budget ] []
    |> Or_error.ok_exn
  in
  let pinout = List.concat_map [ Pinout.Bank.Ui; Uo; Uio ] ~f:(fun bank ->
    List.init 8 ~f:(fun bit ->
      let description = match bank with
        | Ui -> (match bit with
          | 0 | 1 -> "Command: read / stage address / stage low byte / write"
          | 2 -> "Read high byte" | 3 | 4 -> "Bank select" | _ -> "Unused")
        | Uo -> "Selected response byte"
        | Uio -> "Address or write-data byte; input only"
      in
      { Pinout.bank; bit; description }))
  in
  Chip_target.create ~name:"sram_budget"
    ~metadata:{ title = "Three-bank SRAM budget"; author = "hardcaml_asic_example"
              ; description = sprintf "Three 256x16 banks, %d SRAM slots" budget }
    ~source_inputs:(extra_inputs @ ["dune-project"; "asic-dependency.json"; "asics/sram_budget/dune";
                    "asics/sram_budget/sram_budget.ml"])
    ~design:(module Design)
    ~target:{ harness = Tiny_tapeout { tiles = T6x4 }; technology = Technology.ihp_sg13cmos5l }
    ~flow:(Flow.librelane ~overrides:(Tt_cmos5l.overrides ()) Synthesis)
    ~clocks:[{port = "clk"; period = Time_float.Span.of_ns 20.}]
    ~pinout ~policy ()
;;

(* The manifest records the selected bank configuration as well as its effect
   on all three resolved requests. Derive the limit from the checked value. *)
let project = chip_target

let registered_chip_target ~extra_inputs ~variant_id () =
  let open Or_error.Let_syntax in
  let key = "bank_variant" in
  let slots = [ "two_slot", 2; "three_slot", 3 ] in
  let%bind parameter = Hardware_variant.Parameter.create ~key
    ~kind:(Enumeration (List.map slots ~f:fst)) in
  let%bind schema = Hardware_variant.Schema.create ~design_id:"sram_budget"
    ~schema_id:"sram_budget.v1" ~parameters:[parameter] in
  let%bind variant = Hardware_variant.create ~schema ~assignments:[key, Enum variant_id] in
  Chip_target.of_variant ~variant ~create:(fun checked ->
    let%bind id = Hardware_variant.get_enum checked ~key in
    chip_target ~extra_inputs ~budget:(List.Assoc.find_exn slots id ~equal:String.equal) ())
;;

let registered_project = registered_chip_target

let catalog () =
  let methodology = Flow.Methodology.create ~id:"standard" ~label:"Standard"
    ~description:"Synthesis of three banks with a bounded stock SRAM allocation"
    ~backend_recipe:Librelane_classic_v1 ~endpoints:[ Synthesis ]
    ~configurable:Flow.Parameter.Key.all ~defaults:[] |> Or_error.ok_exn in
  let profile = Flow.Profile.create ~id:"balanced" ~label:"Balanced"
    ~description:"Area-oriented synthesis baseline"
    ~assignments:[Flow.Parameter.synth_strategy Area_0; Flow.Parameter.synth_abc_buffering false]
    |> Or_error.ok_exn in
  let entry = Flow.Catalog.Entry.create ~methodology ~profiles:[profile]
    ~default_profile:"balanced" |> Or_error.ok_exn in
  Flow.Catalog.create ~entries:[entry] ~default_flow:"standard" ~default_profile:"balanced"
  |> Or_error.ok_exn
;;
