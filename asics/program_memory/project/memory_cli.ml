open! Core
open Hardcaml_asic

let usage =
   "Usage: memory_cli (check|emit|prepare|preview|resources) --selection (flops|exact|fallback) --operation (synthesis|hardening)\n\
    \       prepare requires --source-root ROOT --results-root STORE; optional --json\n\
    \       resources is nonpublishing; optional --simulation; --depth 128|256 (default 256)\n\
    \       preview requires --source-root ROOT; nonpublishing implementation preparation\n\
   \       emit also requires --source-root ROOT --output-dir NEW_OR_EMPTY_DIR\n"
;;

let main () =
  let bad () = Out_channel.output_string stderr usage; Stdlib.exit 2 in
  let args = Array.to_list (Sys.get_argv ()) |> List.tl_exn in
  match args with
  | [ "--help" ] -> Out_channel.output_string stdout usage
  | command :: rest when List.mem [ "check"; "emit"; "prepare"; "preview"; "resources" ] command ~equal:String.equal ->
    let rec parse acc = function
       | [] -> acc
       | ("--json" | "--simulation" as key) :: rest
         when not (List.Assoc.mem acc key ~equal:String.equal) -> parse ((key, "true") :: acc) rest
      | key :: value :: rest
         when List.mem [ "--selection"; "--operation"; "--source-root"; "--output-dir"; "--results-root"; "--depth" ] key ~equal:String.equal
             && not (List.Assoc.mem acc key ~equal:String.equal) ->
        parse ((key, value) :: acc) rest
      | _ -> bad ()
    in
    let options = parse [] rest in
    let get key = List.Assoc.find options key ~equal:String.equal in
    let requirement =
      match get "--selection" with
      | Some "flops" -> Resource_policy.Requirement.Flops
       | Some "exact" -> Exact
       | Some "fallback" -> Exact_or_flop_fallback
      | _ -> bad ()
    in
    let operation =
      match get "--operation" with
      | Some "synthesis" -> Flow.Operation.Synthesis
      | Some "hardening" -> Hardening
      | _ -> bad ()
     in
     let depth = match get "--depth" with None | Some "256" -> 256 | Some "128" -> 128 | _ -> bad () in
     if Option.is_some (get "--simulation") && not (String.equal command "resources") then bad ();
     if Option.is_some (get "--results-root") && not (String.equal command "prepare") then bad ();
     if String.equal command "prepare" then (
       let source_root, store = match get "--source-root", get "--results-root", get "--output-dir" with
         | Some root, Some store, None -> root, store | _ -> bad () in
       let module E = Hardcaml_asic_execution in
       let request = E.Identity_json.parse (Yojson.Safe.to_string (`Assoc
         [ "selection", `String (Option.value_exn (get "--selection"))
         ; "operation", `String (Option.value_exn (get "--operation"))
         ; "depth", `Int depth; "source_root", `String source_root ]))
         |> Result.map_error ~f:E.Identity_json.error_message |> Result.ok_or_failwith in
       let outcome = E.Preparation_service.run_cli ~store ~request
         ~json:(Option.is_some (get "--json"))
         ~prepare:(fun ~on_phase ->
           let project = Program_memory.project ~depth ~operation requirement |> Or_error.ok_exn in
           Project.prepare_resources ~on_phase project ~source_root) () in
       Stdlib.exit (Option.value outcome.record.exit_code ~default:1));
     let result =
      let open Or_error.Let_syntax in
       let%bind project = Program_memory.project ~depth ~operation requirement in
       match command, get "--source-root", get "--output-dir" with
       | "preview", Some source_root, None ->
         (match Project.prepare_resources project ~source_root with
          | Ok prepared -> Ok (Resource_preparation.to_json prepared)
          | Error failure ->
            print_endline (Yojson.Safe.pretty_to_string (Resource_preparation.Failure.to_json failure));
            Stdlib.exit 1)
       | "check", None, None ->
        let%map resolved = Project.elaborate_for_flow project in
        `Assoc
          [ "resources_sexp",
            `String (Sexp.to_string_hum
              ([%sexp_of: Resource.Record.t list]
                  (Elaborated_project.resources resolved.elaborated_project))) ]
       | "resources", None, None ->
         let%map view = if Option.is_some (get "--simulation") then
           Project.elaborate project ~mode:Simulation |> Or_error.map ~f:Resource_snapshot.of_elaborated
         else Project.elaborate_for_flow project |> Or_error.map ~f:Resource_snapshot.of_resolved in
         Resource_snapshot.to_json view
      | "emit", Some source_root, Some output_dir ->
        let%map bundle = Project.emit_bundle project ~source_root ~output_dir in
        `Assoc [ "identity", `String (Bundle.identity bundle); "output_dir", `String output_dir ]
      | _ -> bad ()
    in
    (match result with
     | Ok json -> print_endline (Yojson.Safe.pretty_to_string json)
     | Error error ->
       eprintf "%s\n%!" (Error.to_string_hum error);
       Stdlib.exit 1)
  | _ -> bad ()
;;

let () =
  try main () with exn ->
    eprintf "memory_cli failed: %s\n%!" (Exn.to_string exn);
    Stdlib.exit 2
;;
