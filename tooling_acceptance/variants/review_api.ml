open Hardcaml_asic_execution

let () =
  try
    let value = match Array.to_list Sys.argv with
      | [_; "archive-inspect"; path] ->
        let result = Archive_service.inspect ~run_dir:path in
        `Assoc ["bundle_source", `String result.bundle_source;
                "members", `Int (List.length result.bundle_files)]
      | [_; "report"; path] ->
        let result = Report_service.run ~render_human:false ~strict_sources:true path in
        `Assoc ["accepted", `Bool (Report_service.accepted result.verdict);
                "metadata", `List result.metadata_sources; "results", result.results]
      | _ -> invalid_arg "archive-inspect RUN | report RUN"
    in
    print_endline (Evidence_json.record_bytes value)
  with
  | Invalid_argument message | Failure message | Sys_error message ->
    prerr_endline message; exit 2
  | Unix.Unix_error (error, operation, path) ->
    prerr_endline (operation ^ " " ^ path ^ ": " ^ Unix.error_message error); exit 2
