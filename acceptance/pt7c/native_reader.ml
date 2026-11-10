(* Independent acceptance adapter: all interpretation belongs to the provider. *)
open Hardcaml_asic_execution

let read path =
  let channel = open_in_bin path in
  Fun.protect ~finally:(fun () -> close_in channel) (fun () ->
    really_input_string channel (in_channel_length channel))

let () =
  match Array.to_list Sys.argv with
  | [_; resolution; directory; top] ->
    let resolved = match Yojson.Safe.from_file resolution with
      | `List rows -> rows
      | _ -> failwith "resolution rows must be a JSON list" in
    let source name = read (Filename.concat directory name) in
    (match Timing_native_coverage.inspect ~top ~resolved
       ~native_sdc:(source "native-state.sdc") ~native_data:(source "native-data.json")
       ~native_checks:(source "native-checks.rpt") ~native_endpoints:(source "native-endpoints.rpt") with
     | Ok value -> print_string (Evidence_json.record_bytes value)
     | Error error -> prerr_endline error; exit 2)
  | _ -> prerr_endline "native_reader RESOLUTION_ROWS_JSON NATIVE_DIRECTORY VERIFIED_TOP"; exit 2
