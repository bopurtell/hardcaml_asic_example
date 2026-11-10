open! Core
open Hardcaml_asic

(* Only preparation/publication: execution uses the frozen public provider inputs. *)
let main command source_root profile output expected =
  let open Or_error.Let_syntax in
  let%bind catalog = Named_catalog.create () in
  let%bind selection = Flow.Selection.create ~flow:"timing_synthesis" ~profile () in
  let%bind project = Timing_project.create ~scalar_source:true () in
  let%bind prepared =
    Methodology_plan.prepare ~catalog ~selection ~endpoint:Flow.Stage.Synthesis
      ~catalog_inputs:Named_catalog.source_inputs ?expected_plan_identity:expected
      project ~source_root
  in
  let plan = Methodology_plan.Prepared.plan prepared in
  match command, output with
  | "plan", None -> Ok (Methodology_plan.to_yojson plan)
  | "emit", Some store_dir ->
    let bundle = Methodology_plan.Prepared.bundle prepared in
    let%map publication = Bundle.publish bundle ~store_dir in
    `Assoc
      [ "schema_version", `Int 1
      ; "kind", `String "bundle_emission"
      ; "bundle_identity", `String (Bundle.identity bundle)
      ; "plan_identity", `String (Methodology_plan.plan_identity plan)
      ; "output_dir", `String publication.directory
      ; "reused", `Bool publication.reused
      ; "plan", Methodology_plan.to_yojson plan
      ]
  | _ -> Or_error.error_string "Invalid command arguments"
;;

let () =
  let result =
    match Array.to_list (Sys.get_argv ()) with
    | [ _; "plan"; root; profile ] -> main "plan" root profile None None
    | [ _; "emit"; root; profile; store; expected ] ->
      main "emit" root profile (Some store) (Some expected)
    | _ -> Or_error.error_string
      "Usage: named_timing_cli plan SOURCE_ROOT PROFILE | emit SOURCE_ROOT PROFILE STORE EXPECTED_PLAN_IDENTITY"
  in
  match result with
  | Ok value -> printf "%s\n%!" (Yojson.Safe.pretty_to_string value)
  | Error error -> eprintf "%s\n%!" (Error.to_string_hum error); Stdlib.exit 1
;;
