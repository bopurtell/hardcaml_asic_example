open! Core
open Hardcaml
open Hardcaml_asic

let require label condition = if not condition then failwith label

let check_inventory requirement mode elaborated =
  let r = List.hd_exn (Elaborated_project.resources elaborated) in
  require "exactly one registered resource" (List.length (Elaborated_project.resources elaborated) = 1);
  require "stable program ID" (String.equal (Resource.Id.to_string r.id) "program");
  require "RAM kind" (String.equal r.request.kind "single_port_ram");
  require "exact 256x16 1RW contract"
    (Sexp.equal r.request.contract
       (Sexp.of_string
          "((width 16) (depth 256) (read_latency 1) (port 1rw) (disabled_output hold) (write_output unspecified))"));
  require "instance policy, not default"
    (Resource_policy.Applied.equal r.policy
       (Rule (Resource_policy.Selector.instance_exn "program")));
  require "explicit requirement" (Resource_policy.Requirement.equal r.requirement requirement);
  (match requirement with
   | Resource_policy.Requirement.Flops ->
     require "Flops implementation" (Resource.Selection.Implementation.equal r.selection.implementation Flops);
     require "explicit, not fallback" (Resource.Selection.Reason.equal r.selection.reason Explicit_flops)
   | Exact ->
     require "stock macro implementation"
       (Resource.Selection.Implementation.equal r.selection.implementation
          (Macro "RM_IHPSG13_1P_256x16_c2_bm_bist"));
     require "exact, not fallback" (Resource.Selection.Reason.equal r.selection.reason
       (Exact_mapping { technology = "ihp-sg13cmos5l" }))
   | _ -> failwith "test requires explicit selection");
  let expected_as, expected_sources =
    match mode with
    | Elaboration.Mode.Simulation ->
      Resource.Record.Elaborated_as.Behavioral_model, [ Resource.Record.Source.Generated_behavioral_model ]
    | Implementation -> Selected_implementation, [ Generated_synthesis_rtl ]
  in
  require "mode-specific elaboration" (Resource.Record.Elaborated_as.equal r.elaborated_as expected_as);
  if Resource_policy.Requirement.equal requirement Exact
     && Elaboration.Mode.equal mode Implementation
  then require "complete macro collateral" (List.length r.sources = 11)
  else require "mode-specific generated sources"
    ([%equal: Resource.Record.Source.t list] r.sources expected_sources)
;;

module Core_design = struct
  include Program_memory
  let name = "program_memory_core"
end

let core_project requirement =
  Project.create ~name:"program_memory_core_test"
    ~metadata:{ title = "Memory test"; author = "test"; description = "Public core API test" }
    ~design:(module Core_design)
    ~target:{ harness = Tiny_tapeout { tiles = T6x4 }; technology = Technology.ihp_sg13cmos5l }
    ~flow:(Flow.librelane Synthesis)
    ~policy:(Program_memory.policy requirement |> Or_error.ok_exn) ()
  |> Or_error.ok_exn
;;

let run_core requirement mode =
  let elaborated = Project.elaborate (core_project requirement) ~mode |> Or_error.ok_exn in
  check_inventory requirement mode elaborated;
  let sim = Cyclesim.create (Elaborated_project.circuit elaborated) in
  let output edge = Cyclesim.out_port ~clock_edge:edge sim "read_data" in
  let before = output Before and after = output After in
  let known_response = ref None in
  let edges = ref 0 in
  let check phase port expected =
    let actual = Bits.to_int_trunc !port in
    if actual <> expected then
      raise_s [%message "memory mismatch" (!edges : int) (phase : string) (expected : int) (actual : int)]
  in
  let edge ~enable ~write address data expected =
    List.iter [ "enable", 1, enable; "write_enable", 1, write
              ; "address", 8, address; "write_data", 16, data ]
      ~f:(fun (name, width, value) -> Cyclesim.in_port sim name := Bits.of_int_trunc ~width value);
    Cyclesim.cycle_check sim;
    Cyclesim.cycle_before_clock_edge sim;
    Option.iter !known_response ~f:(check "before edge: latency/hold" before);
    Cyclesim.cycle_at_clock_edge sim;
    Cyclesim.cycle_after_clock_edge sim;
    Option.iter expected ~f:(check "after edge" after);
    known_response := expected;
    Int.incr edges
  in
  let word a = ((a * 257) lxor 0xa53c) land 0xffff in
  (* Load every location. Write responses are intentionally never observed. *)
  for a = 0 to 255 do edge ~enable:1 ~write:1 a (word a) None done;
  (* Consecutive permuted reads catch asynchronous/extra-latency/address errors. *)
  for n = 0 to 255 do
    let a = (n * 73 + 19) land 255 in
    let expected = word a in
    edge ~enable:1 ~write:0 a 0 (Some expected);
    edge ~enable:0 ~write:0 ((a + 1) land 255) 0 (Some expected);
    edge ~enable:0 ~write:1 a (expected lxor 0xffff) (Some expected)
  done;
  (* Verify disabled writes did not modify any word. *)
  for a = 255 downto 0 do edge ~enable:1 ~write:0 a 0 (Some (word a)) done;
  (* Real overwrites, including 0xffff and 0x0000, then reload all addresses. *)
  for a = 0 to 255 do edge ~enable:1 ~write:1 a ((a land 1) * 0xffff) None done;
  for a = 0 to 255 do edge ~enable:1 ~write:0 a 0 (Some ((a land 1) * 0xffff)) done;
  printf "PASS memory %s %s: %d edges, full load/read/overwrite, latency-one, disabled read/write hold\n%!"
    (Sexp.to_string ([%sexp_of: Resource_policy.Requirement.t] requirement))
    (Sexp.to_string ([%sexp_of: Elaboration.Mode.t] mode)) !edges
;;

let () =
  if Array.equal String.equal (Sys.get_argv ()) [| (Sys.get_argv ()).(0); "--export-exact-core" |]
  then (
    let elaborated = Project.elaborate (core_project Exact) ~mode:Implementation |> Or_error.ok_exn in
    Rtl.print Verilog (Elaborated_project.circuit elaborated);
    Stdlib.exit 0);
  List.iter [ Elaboration.Mode.Simulation; Implementation ] ~f:(run_core Flops);
  run_core Exact Simulation;
  List.iter [ Elaboration.Mode.Simulation; Implementation ] ~f:(fun mode ->
    let project = Program_memory.project Flops |> Or_error.ok_exn in
    Project.elaborate project ~mode |> Or_error.ok_exn |> check_inventory Flops mode;
    let exact = Program_memory.project Exact |> Or_error.ok_exn in
    Project.elaborate exact ~mode |> Or_error.ok_exn |> check_inventory Exact mode);
  List.iter [ true; false ] ~f:(fun with_macro_intent ->
    Program_memory.project ~with_macro_intent Exact |> Or_error.ok_exn
     |> Project.elaborate_for_flow |> Or_error.ok_exn |> ignore);
  (* Operation selection must not change the hardware inventory or cycle contract. *)
  List.iter [ Flow.Operation.Synthesis; Hardening ] ~f:(fun operation ->
    List.iter [ Resource_policy.Requirement.Flops; Exact ] ~f:(fun requirement ->
      let project = Program_memory.project ~operation requirement |> Or_error.ok_exn in
      Project.elaborate_for_flow project |> Or_error.ok_exn |> ignore;
      List.iter [ Elaboration.Mode.Simulation; Implementation ] ~f:(fun mode ->
        Project.elaborate project ~mode |> Or_error.ok_exn
         |> check_inventory requirement mode)));
  (match Program_memory.project ~operation:Hardening ~with_macro_intent:false Exact
         |> Or_error.bind ~f:Project.elaborate_for_flow with
   | Ok _ -> failwith "Exact Hardening accepted missing physical intent"
   | Error error ->
     require "Hardening requires complete physical intent"
       (String.is_substring (Error.to_string_hum error)
          ~substring:"hardening requires complete macro placement intent"));
  let module Unsupported = struct
    module I = Program_memory.I
    module O = Program_memory.O
    let name = "unsupported_memory"
    let create context (i : _ I.t) =
      { O.read_data = Single_port_ram.create context ~name:"program"
          (Single_port_ram.Config.create_exn ~width:16 ~depth:128 ~read_latency:1)
          ~clock:i.clock ~enable:i.enable ~write_enable:i.write_enable
          ~address:(Signal.select i.address ~high:6 ~low:0) ~write_data:i.write_data }
  end in
  let unsupported = Project.create ~name:"unsupported_shape"
    ~metadata:{ title = "Unsupported"; author = "test"; description = "No shape rounding" }
    ~design:(module Unsupported)
    ~target:{ harness = Tiny_tapeout { tiles = T6x4 }; technology = Technology.ihp_sg13cmos5l }
    ~flow:(Flow.librelane Synthesis)
    ~policy:(Program_memory.policy Exact |> Or_error.ok_exn) () |> Or_error.ok_exn in
  List.iter [ Elaboration.Mode.Simulation; Implementation ] ~f:(fun mode ->
    match Project.elaborate unsupported ~mode with
    | Ok _ -> failwith "unsupported Exact shape succeeded"
    | Error error -> List.iter [ "program"; "no exact implementation"; "fallback is not permitted" ]
        ~f:(fun substring -> require substring
          (String.is_substring (String.lowercase (Error.to_string_hum error)) ~substring)));
  Program_memory.project Flops |> Or_error.ok_exn |> Project.elaborate_for_flow |> Or_error.ok_exn |> ignore;
  let policy = Program_memory.policy Flops |> Or_error.ok_exn in
  require "no implicit fallback/default for another instance"
    (Or_error.is_error (Resource_policy.lookup policy (Resource.Id.of_string_exn "other")));
  printf "PASS policy: Flops/Exact inventory in both modes; optional intent; unsupported 128x16 rejected in both modes; no fallback; TT resolution\n%!"
;;
