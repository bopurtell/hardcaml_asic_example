open! Core
open Hardcaml_asic

(* Pure companion to project emit: no project/root discovery, EDA or publication. *)
let () =
  try
    let endpoint = ref Flow.Stage.Signoff in
    let initial_boundary = ref None in
    let stage text = Flow.Stage.of_string text |> Or_error.ok_exn in
    Stdlib.Arg.parse
      [ "--endpoint", Stdlib.Arg.String (fun text -> endpoint := stage text), "STAGE Last stage (default signoff)"
      ; "--initial-boundary", Stdlib.Arg.String (fun text -> initial_boundary := Some (stage text)), "STAGE Explicit checkpoint source"
      ]
      (fun _ -> failwith "Unexpected positional argument")
      "stage_recipe [--endpoint STAGE] [--initial-boundary STAGE]";
    let recipe = Flow.Recipe.through ?initial_boundary:!initial_boundary !endpoint |> Or_error.ok_exn in
    printf "%s\n%!" (Flow.Recipe.to_string recipe)
  with exn ->
    eprintf "stage recipe failed: %s\n%!" (Exn.to_string exn);
    Stdlib.exit 2
;;
