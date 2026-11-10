(* Public stat-only source admission; limits belong to the captured provider. *)
open Hardcaml_asic_execution

let () =
  match Array.to_list Sys.argv with
  | _ :: inventory :: external_roots ->
    let paths = match Yojson.Safe.from_file inventory with
      | `List rows -> List.map (function `String path -> path | _ -> failwith "expected path") rows
      | _ -> failwith "expected path list"
    in
    (match Timing_intent_execution.precheck_sources ~external_roots ~paths () with
     | Ok value -> print_string (Evidence_json.record_bytes value)
     | Error error -> prerr_endline error; exit 2)
  | _ -> prerr_endline "Usage: named_precheck ABSOLUTE_PATHS_JSON [CANONICAL_EXTERNAL_ROOT ...]"; exit 2
