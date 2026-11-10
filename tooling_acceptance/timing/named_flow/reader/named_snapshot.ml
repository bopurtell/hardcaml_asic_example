(* Exercise the public captured-snapshot seam without changing retained originals. *)
open Hardcaml_asic_execution

let checked = function Ok value -> value | Error error -> failwith error
let read path =
  let channel = open_in_bin path in
  Fun.protect ~finally:(fun () -> close_in_noerr channel) (fun () ->
    really_input_string channel (in_channel_length channel))

let () =
  try
    match Array.to_list Sys.argv with
    | [ _; execution; captured_raw ] ->
      let execution_sha256 = Identity_json.sha256_bytes (read execution) in
      let raw = match Identity_json.parse (read captured_raw) with
        | Ok raw -> raw
        | Error error -> failwith (Identity_json.error_message error)
      in
      let record, checkpoints = checked (Stage_execution_record.validate_snapshot raw) in
      let view = checked (Timing_intent_execution.inspect_snapshot
        ~execution ~execution_sha256 ~raw ~record ~checkpoints ()) in
      print_string (Evidence_json.record_bytes (Option.value view ~default:`Null))
    | _ -> prerr_endline "Usage: named_snapshot EXACT_EXECUTION_JSON CAPTURED_RAW_JSON"; exit 2
  with Failure error | Invalid_argument error -> prerr_endline error; exit 2
