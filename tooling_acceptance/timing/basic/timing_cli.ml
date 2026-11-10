open! Core
open Hardcaml_asic

let () =
  match Array.to_list (Sys.get_argv ()) with
  | [ _; ("emit" | "emit-scalar" as command); source_root; output_dir ] ->
    let result =
      let open Or_error.Let_syntax in
      let%bind project = Timing_project.create ~scalar_source:(String.equal command "emit-scalar") () in
      let%map bundle = Project.emit_bundle project ~source_root ~output_dir in
      Bundle.identity bundle
    in
    (match result with
     | Ok identity -> print_endline identity
     | Error error -> eprintf "%s\n%!" (Error.to_string_hum error); Stdlib.exit 1)
  | _ ->
    eprintf "Usage: timing_cli (emit|emit-scalar) SOURCE_ROOT NEW_OUTPUT_DIRECTORY\n%!";
    Stdlib.exit 2
;;
