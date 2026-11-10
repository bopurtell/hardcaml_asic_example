open! Core
open Hardcaml
open Hardcaml_asic

let require label condition = if not condition then failwith label
let near a b = Float.(abs (a -. b) < 1e-6)

let () =
  let project = Fifo_asic.project () |> Or_error.ok_exn in
  let r = Project.elaborate_for_flow project |> Or_error.ok_exn in
  let simulation_project = Project.elaborate project ~mode:Simulation |> Or_error.ok_exn in
  let check_elaborated_project elaborated_project =
    let circuit = Elaborated_project.circuit elaborated_project in
    require "exact top" (String.equal (Circuit.name circuit) "tt_um_controlled_fifo");
    let ports signals =
      List.map signals ~f:(fun s -> List.hd_exn (Signal.names s), Signal.width s)
      |> List.sort ~compare:[%compare: string * int]
    in
    let check_ports label actual expected =
      require label
        ([%equal: (string * int) list] (ports actual)
           (List.sort expected ~compare:[%compare: string * int]))
    in
    check_ports "exact input ports" (Circuit.inputs circuit)
      [ "clk", 1; "ena", 1; "rst_n", 1; "ui_in", 8; "uio_in", 8 ];
    check_ports "exact output ports" (Circuit.outputs circuit)
      [ "uo_out", 8; "uio_out", 8; "uio_oe", 8 ];
    require "ordinary FIFO registers are not registered RAM resources"
      (List.is_empty (Elaborated_project.resources elaborated_project));
    require "one clock" (List.length (Elaborated_project.clocks elaborated_project) = 1);
    require "hardening" (Flow.Operation.equal (Elaborated_project.flow elaborated_project).operation Hardening);
    let pins = Elaborated_project.pinout elaborated_project in
    Pinout.validate_tiny_tapeout pins |> Or_error.ok_exn;
    require "all 24 pin descriptions" (List.length pins = 24)
  in
  check_elaborated_project r.elaborated_project;
  check_elaborated_project simulation_project;
  require "implementation mode" (match Elaborated_project.mode r.elaborated_project with Implementation -> true | _ -> false);
  require "separate simulation mode" (match Elaborated_project.mode simulation_project with Simulation -> true | _ -> false);
  require "simulation cannot cross implementation resolution boundary"
    (Or_error.is_error (Resolved_flow.resolve simulation_project));
  require "TT6x4" (String.equal r.target.tiles "6x4");
  require "IHP CMOS5L" (String.equal r.target.technology_name "ihp-sg13cmos5l");
  require "clk at 48MHz"
    (String.equal r.clock.port "clk" && near r.clock_hz 48e6
     && near r.clock_period_ns (1e9 /. 48e6));
  let check_delays delays ports maximum =
    require "exact constrained ports"
      ([%equal: string list]
          (List.map delays ~f:(fun (d : Resolved_flow.Delay_ns.t) -> d.port)) ports);
    List.iter delays ~f:(fun d ->
      require ("delay bounds: " ^ d.port) (near d.minimum 0. && near d.maximum maximum))
  in
  check_delays r.input_delays_ns [ "ena"; "rst_n"; "ui_in"; "uio_in" ] 1.;
  check_delays r.output_delays_ns [ "uio_oe"; "uio_out"; "uo_out" ] 2.;
  let setting key = List.find_exn r.settings ~f:(fun s -> String.equal s.key key) in
  List.iter (Tt_cmos5l.overrides ()) ~f:(fun o ->
    let s = setting o.key in
    require ("template setting: " ^ o.key) (Yojson.Safe.equal s.value o.value);
    require ("template reason: " ^ o.key)
      (match s.owner with Override reason -> String.equal reason o.reason | _ -> false));
  List.iter
    [ "DESIGN_NAME", `String "tt_um_controlled_fifo"
    ; "CLOCK_PORT", `String "clk"
    ; "PDK", `String "ihp-sg13cmos5l"
    ; "FP_SIZING", `String "absolute"
    ]
    ~f:(fun (key, expected) ->
      require ("resolved setting: " ^ key) (Yojson.Safe.equal (setting key).value expected));
  require "resolved clock setting"
    (match (setting "CLOCK_PERIOD").value with `Float n -> near n (1e9 /. 48e6) | _ -> false);
  printf "PASS resolution: exact TT ports, TT6x4/CMOS5L, 48MHz, min/max delays, template settings, 24 pins, empty resource inventory; separate Simulation\n%!"
;;
