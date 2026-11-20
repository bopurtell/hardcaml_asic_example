open! Core
open Hardcaml_asic

let emit ~budget ~source_root ~output_dir =
  let project = Sram_budget.project ~extra_inputs:["asics/sram_budget/emit.ml"] ~budget () |> Or_error.ok_exn in
  Project.emit_bundle project ~source_root ~output_dir |> Or_error.ok_exn |> Bundle.identity
;;

let () =
  match Array.to_list (Sys.get_argv ()) with
  | [ _; ("0" | "1" | "2" | "3" as slots); source_root; output_dir ] ->
    print_endline (emit ~budget:(Int.of_string slots) ~source_root ~output_dir)
  | _ -> eprintf "Usage: emit SLOTS(0..3) SOURCE_ROOT NEW_OR_EMPTY_OUTPUT_DIR\n"; Stdlib.exit 2
;;
