open! Core
open Hardcaml_asic

(* This explicit command is the opt-in. Ordinary Project emission remains unchanged.
   Render exactly once using the public physical qualification seam, then publish
   those same bytes. No emitted SDC, RTL, manifest or config is rewritten. *)
let emit ~full ~source_root ~output_dir =
  let open Or_error.Let_syntax in
  let%bind project = Physical_project.create ~full in
  let%bind resolved = Project.elaborate_for_flow project in
  let%bind simulation_project = Project.elaborate project ~mode:Simulation in
  let%bind bundle =
    Elaboration.Bundle.render ~timing_physical_qualification:true
      ~simulation_project ~source_root ~input_paths:Physical_project.source_inputs resolved
  in
  let%map () = Bundle.write bundle ~output_dir in
  `Assoc [ "bundle_identity", `String (Bundle.identity bundle)
         ; "output_dir", `String output_dir
         ; "stage", `String (if full then "full" else "synthesis")
         ; "manifest", Bundle.manifest bundle ]
;;

let () =
  let result =
    match Array.to_list (Sys.get_argv ()) with
    | [ _; "emit-physical"; ("synthesis" | "full" as stage); source_root; output_dir ] ->
      emit ~full:(String.equal stage "full") ~source_root ~output_dir
    | _ -> Or_error.error_string
      "Usage: physical_timing_cli emit-physical (synthesis|full) SOURCE_ROOT NEW_OUTPUT_DIRECTORY"
  in
  match result with
  | Ok value -> printf "%s\n%!" (Yojson.Safe.pretty_to_string value)
  | Error error -> eprintf "%s\n%!" (Error.to_string_hum error); Stdlib.exit 1
;;
