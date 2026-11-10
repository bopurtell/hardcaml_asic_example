(* Pass-through public inventory adapter. No local timing interpretation. *)
open Hardcaml_asic_execution

let () =
  match Array.to_list Sys.argv with
  | [ _; execution ] ->
    (match Timing_intent_execution.source_files ~execution () with
     | Ok sources -> print_string (Evidence_json.record_bytes (`List sources))
     | Error error -> prerr_endline error; exit 2)
  | _ -> prerr_endline "Usage: named_sources EXACT_EXECUTION_JSON"; exit 2
