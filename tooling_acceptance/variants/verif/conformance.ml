open! Core
open Hardcaml
open Hardcaml_asic

let require label condition = if not condition then failwith label

let inventory checked requirement elaborated =
  let depth = Hardware_variant.get_int checked ~key:"depth" |> Or_error.ok_exn in
  let rows = Elaborated_project.resources elaborated in
  require "exactly one resource" (List.length rows = 1);
  let r = List.hd_exn rows in
  require "program identity" (String.equal (Resource.Id.to_string r.id) "program");
  require "actual RAM request" (String.equal r.request.kind "single_port_ram");
  require "instance-specific policy, not default"
    (Resource_policy.Applied.equal r.policy
       (Rule (Resource_policy.Selector.instance_exn "program")));
  require "actual registered shape matches checked assignment"
    (Sexp.equal r.request.contract
       (Sexp.of_string (sprintf
         "((width 16) (depth %d) (read_latency 1) (port 1rw) (disabled_output hold) (write_output unspecified))" depth)));
  require "same declaration on elaboration"
    (String.equal (Hardware_variant.identity checked)
       (Hardware_variant.identity (Option.value_exn (Elaborated_project.hardware_variant elaborated))));
  require "explicit requirement" (Resource_policy.Requirement.equal r.requirement requirement);
  (match requirement with
   | Flops ->
     require "explicit flops" (Resource.Selection.Implementation.equal r.selection.implementation Flops);
     require "no fallback" (Resource.Selection.Reason.equal r.selection.reason Explicit_flops)
   | Exact -> require "exact stock macro"
       (Resource.Selection.Implementation.equal r.selection.implementation
          (Macro "RM_IHPSG13_1P_256x16_c2_bm_bist"))
   | _ -> failwith "no fallback in PT8")
;;

(* Independent behavioral oracle: expected values depend on the declared depth,
   never on the constructor's effective configuration or returned resource record. *)
let behavior depth elaborated =
  let sim = Cyclesim.create (Elaborated_project.circuit elaborated) in
  let before = Cyclesim.out_port ~clock_edge:Before sim "read_data" in
  let after = Cyclesim.out_port ~clock_edge:After sim "read_data" in
  let known = ref None and edges = ref 0 in
  let check phase port expected =
    let actual = Bits.to_int_trunc !port in
    require (sprintf "%s edge%d expected=%04x actual=%04x" phase !edges expected actual)
      (actual = expected) in
  let edge enable write address data expected =
    List.iter [ "enable", 1, enable; "write_enable", 1, write
              ; "address", 8, address; "write_data", 16, data ]
      ~f:(fun (name, width, value) -> Cyclesim.in_port sim name := Bits.of_int_trunc ~width value);
    Cyclesim.cycle_check sim;
    Cyclesim.cycle_before_clock_edge sim;
    Option.iter !known ~f:(check "latency-one before edge" before);
    Cyclesim.cycle_at_clock_edge sim;
    Cyclesim.cycle_after_clock_edge sim;
    Option.iter expected ~f:(check "after edge" after);
    known := expected; Int.incr edges in
  let word a = ((a * 257) lxor 0xa53c) land 0xffff in
  for a = 0 to depth - 1 do edge 1 1 a (word a) None done;
  for n = 0 to depth - 1 do
    let a = (n * 73 + 19) mod depth in
    edge 1 0 a 0 (Some (word a));
    edge 0 0 ((a + 1) mod depth) 0 (Some (word a));
    edge 0 1 a 0xffff (Some (word a))
  done;
  for a = depth - 1 downto 0 do edge 1 0 a 0 (Some (word a)) done;
  (* Discriminate 128/256 capacity independently of the resource declaration. *)
  edge 1 1 0 0x1234 None;
  edge 1 1 128 0xabcd None;
  edge 1 0 0 0 (Some (if depth = 128 then 0xabcd else 0x1234));
  edge 1 0 128 0 (Some 0xabcd);
  edge 1 1 (depth - 1) 0xffff None;
  edge 1 0 (depth - 1) 0 (Some 0xffff);
  printf "PASS behavioral depth%d width16 latency1: %d edges; full capacity, hold, disabled writes, boundary128\n%!" depth !edges
;;

let () =
  let ignored = match Array.to_list (Sys.get_argv ()) with
    | [ _; "ignored" ] -> true | [ _; "valid" ] -> false | _ -> failwith "valid|ignored" in
  let run depth requirement mode =
    let checked = Variant_memory.variant depth |> Or_error.ok_exn in
    let project = Variant_memory.project ~core_ports:true ~ignore_depth:ignored checked requirement |> Or_error.ok_exn in
    let elaborated = Project.elaborate project ~mode |> Or_error.ok_exn in
    if ignored then (
      let rejected label f =
        match Or_error.try_with f with
        | Ok () -> failwith (label ^ " ignored-depth unexpectedly passed")
        | Error e -> printf "EXPECTED CONFORMANCE FAILURE %s: %s\n%!" label (Error.to_string_hum e) in
      rejected "registered request" (fun () -> inventory checked requirement elaborated);
      rejected "capacity/address boundary" (fun () -> behavior depth elaborated);
      Stdlib.exit 1)
    else (inventory checked requirement elaborated; behavior depth elaborated) in
  if ignored then run 128 Flops Implementation
  else (
    List.iter [128; 256] ~f:(fun depth ->
      List.iter [Elaboration.Mode.Implementation; Simulation] ~f:(run depth Flops));
    run 256 Exact Simulation;
    List.iter [Elaboration.Mode.Implementation; Simulation] ~f:(fun mode ->
      let checked = Variant_memory.variant 128 |> Or_error.ok_exn in
      let project = Variant_memory.project ~core_ports:true checked Exact |> Or_error.ok_exn in
      match Project.elaborate project ~mode with
      | Ok _ -> failwith "unsupported Exact128 passed"
      | Error error ->
        require "no exact implementation" (String.is_substring
          (String.lowercase (Error.to_string_hum error)) ~substring:"no exact implementation");
        printf "PASS Exact128 rejected: %s\n%!" (Error.to_string_hum error));
    let hole = Variant_memory.variant 192 |> Or_error.ok_exn in
    require "schema range hole rejected by factory"
      (Or_error.is_error (Variant_memory.project hole Flops));
    printf "PASS five functional simulations; ignored negative is a separate sixth\n%!")
;;
