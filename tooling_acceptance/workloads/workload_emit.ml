open! Core
open Hardcaml_asic
open Hardcaml

(* Direct edge adapter: all address bits are live; the high data byte equals
   address, allowing sixteen-bit observations over the TT's two output banks.
   rst_n is the active-low write command, never a RAM reset. *)
let project ~ignored_address checked requirement =
  Project.of_variant ~variant:checked ~create:(fun checked ->
    let open Or_error.Let_syntax in
    let%bind _ = Variant_memory.shape checked in
    let%bind policy = Resource_policy.create
      [{ selector = Resource_policy.Selector.instance_exn "program"; requirement }] in
    let module D = struct
      module I = Tt_cmos5l.I
      module O = Tt_cmos5l.O
      let name = "tt_um_pt8_workload"
      let create context (i : _ I.t) =
        let open Signal in
        let m = Variant_memory.core ~ignore_depth:false checked context
          { clock = i.clk; enable = i.ena; write_enable = ~:(i.rst_n)
          ; address = (if ignored_address then concat_msb [zero 1; select i.ui_in ~high:6 ~low:0] else i.ui_in)
          ; write_data = concat_msb [i.ui_in; i.uio_in] } in
        { O.uo_out = select m.read_data ~high:7 ~low:0
        ; uio_out = select m.read_data ~high:15 ~low:8; uio_oe = zero 8 }
    end in
    Project.create ~name:"pt8_workload" ~source_inputs:(Variant_memory.source_inputs @
      ["tooling_acceptance/workloads/dune"; "tooling_acceptance/workloads/workload_emit.ml"])
      ~metadata:{ title = "PT8 workload"; author = "hardcaml_asic_example"
                ; description = "Direct latency-one workload adapter" }
      ~design:(module D)
      ~target:{ harness = Tiny_tapeout { tiles = T6x4 }; technology = Technology.ihp_sg13cmos5l }
      ~flow:(Flow.librelane Synthesis)
      ~clocks:[{Clock.port = "clk"; period = Time_float.Span.of_ns 20.}]
      ~pinout:(List.concat_map [Pinout.Bank.Ui; Uo; Uio] ~f:(fun bank ->
        List.init 8 ~f:(fun bit -> {Pinout.bank; bit; description = "Direct workload bit"})))
      ~policy ())

let () =
  let result = Or_error.try_with_join (fun () ->
    let args = Sys.get_argv () in
    let checked = Variant_memory.variant 256 |> Or_error.ok_exn in
    let requirement = match args.(2) with
      | "flops" | "flops-ignored" -> Resource_policy.Requirement.Flops
      | "exact" -> Exact | _ -> failwith "expected flops|exact" in
    let open Or_error.Let_syntax in
    let%bind project = project ~ignored_address:(String.equal args.(2) "flops-ignored") checked requirement in
    let%bind rendered = Project.render_result project ~source_root:args.(1) in
    let bundle = Project.Rendered.bundle rendered in
    let%map published = Bundle.publish bundle ~store_dir:args.(3) in
    `Assoc [ "bundle", `String published.directory
           ; "bundle_identity", `String (Bundle.identity bundle)
           ; "hardware_variant", Hardware_variant.to_yojson checked ]) in
  match result with
  | Ok value -> printf "%s\n%!" (Yojson.Safe.pretty_to_string value)
  | Error error -> eprintf "%s\n%!" (Error.to_string_hum error); Stdlib.exit 2
