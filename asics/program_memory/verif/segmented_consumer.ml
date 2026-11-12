(* Private qualification adapter. It never selects or edits the main FIFO project. *)
module U = Unix
open! Core
open Hardcaml_asic

let catalog_inputs =
  [ "asics/program_memory/verif/segmented_consumer.ml"
  ; "asics/program_memory/verif/dune"
  ]
;;

let project () = Program_memory.project ~operation:Hardening Exact |> Or_error.ok_exn

let catalog () =
  let methodology = Flow.Methodology.create ~id:"stock256-r0" ~label:"Stock 256x16 R0"
    ~description:"Bounded program-memory qualification through Timing"
    ~backend_recipe:Librelane_classic_v1
    ~endpoints:[ Synthesis; Floorplan; Placement; Cts; Routing; Timing ]
    ~configurable:Flow.Parameter.Key.all ~defaults:[] |> Or_error.ok_exn in
  let profile = Flow.Profile.create ~id:"qualification" ~label:"Qualification"
    ~description:"Unmodified public stock physical settings" ~assignments:[] |> Or_error.ok_exn in
  let entry = Flow.Catalog.Entry.create ~methodology ~profiles:[profile]
    ~default_profile:"qualification" |> Or_error.ok_exn in
  Flow.Catalog.create ~entries:[entry] ~default_flow:"stock256-r0"
    ~default_profile:"qualification" |> Or_error.ok_exn
;;

let prepare source_root endpoint =
  let project = project () in
  let catalog = catalog () in
  let methodology = Flow.Catalog.resolve catalog ~endpoint () |> Or_error.ok_exn in
  let preparation = match Project.prepare_resources ~methodology
    ~catalog_inputs project ~source_root with
    | Ok p -> p
    | Error e -> failwith (Yojson.Safe.to_string (Resource_preparation.Failure.to_json e)) in
  let json = Resource_preparation.to_json preparation in
  let decoded = Resource_preparation.of_json json |> Or_error.ok_exn in
  assert (String.equal (Resource_preparation.identity preparation) (Resource_preparation.identity decoded));
  project, catalog, json
;;

let usage =
  "Usage: segmented_consumer flow (list|describe|plan|emit) [OPTIONS]\n\
   \       segmented_consumer (prepare|preview|describe) [OPTIONS]\n\
   \       segmented_consumer prepare SOURCE_ROOT ENDPOINT\n\
   \       segmented_consumer export SOURCE_ROOT NEW_BUNDLE ENDPOINT"
;;

let bad message = raise (Stdlib.Arg.Bad (message ^ "\n" ^ usage))
let checked = Or_error.ok_exn
let absolute path = if Filename.is_relative path then Filename.concat (U.getcwd ()) path else path
let is_file path = try Poly.equal (U.stat path).st_kind U.S_REG with _ -> false

type options =
  { json : bool
  ; flow : string option
  ; profile : string option
  ; endpoint : string option
  ; source : string option
  ; root : string option
  ; results : string option
  ; expected : string option
  ; request : Flow.Parameter.assignment list
  }

(* Same typed selection/options and provider-owned wire encoders as fifo_demo's
   project CLI. No provider invocation or execution authority lives in this CLI. *)
let parse command allowed args =
  let json = ref false and verbose = ref false in
  let flow = ref None and profile = ref None and endpoint = ref None in
  let source = ref None and root = ref None and results = ref None and expected = ref None in
  let request = ref [] in
  let opt name dest = name, Stdlib.Arg.String (fun text ->
    if String.is_empty text || String.is_prefix text ~prefix:"--" then bad (name ^ " requires a value");
    if Option.is_some !dest then bad ("Duplicate option " ^ name);
    dest := Some text), "VALUE" in
  let set text =
    match String.lsplit2 text ~on:'=' with
    | None -> bad "--set requires KEY=VALUE"
    | Some (key, value) ->
      let descriptor = Flow.Parameter.Key.of_string key |> checked |> Flow.Parameter.descriptor in
      let assignment = match Flow.Parameter.value_type descriptor with
        | Enum -> Flow.Parameter.of_string_value ~key value |> checked
        | Boolean ->
          (match Yojson.Safe.from_string value with
           | `Bool value -> Flow.Parameter.of_bool_value ~key value |> checked
           | _ -> bad "--set boolean requires a JSON boolean scalar") in
      request := assignment :: !request
  in
  let specs =
    [ "--json", Stdlib.Arg.Set json, "Versioned JSON output"
    ; "--verbose", Stdlib.Arg.Set verbose, "Diagnostics on stderr"
    ; opt "--flow" flow; opt "--profile" profile; opt "--endpoint" endpoint
    ; opt "--source-root" source; opt "--project-root" root
    ; opt "--results-root" results; opt "--expected-plan-identity" expected
    ; "--set", Stdlib.Arg.String set, "KEY=VALUE Typed supported parameter override"
    ] |> List.filter ~f:(fun (name, _, _) -> List.mem allowed name ~equal:String.equal) in
  Stdlib.Arg.parse_argv ~current:(ref 0) (Array.of_list (("segmented_consumer " ^ command) :: args))
    specs (fun arg -> bad ("Unexpected argument: " ^ arg)) usage;
  ignore !verbose;
  Option.iter !expected ~f:(fun identity ->
    if String.length identity <> 64 || not (String.for_all identity ~f:(function '0'..'9' | 'a'..'f' -> true | _ -> false))
    then bad "--expected-plan-identity requires a lowercase SHA-256");
  { json = !json; flow = !flow; profile = !profile; endpoint = !endpoint
  ; source = !source; root = !root; results = !results; expected = !expected
  ; request = Flow.Parameter.check_assignments ~configurable:Flow.Parameter.Key.all !request |> checked
  }
;;

let common = [ "--json"; "--verbose" ]
let selection_options = [ "--flow"; "--profile"; "--endpoint"; "--set" ]
let root_options = [ "--source-root"; "--project-root" ]
let print options json =
  print_endline (if options.json then Yojson.Safe.to_string json else Yojson.Safe.pretty_to_string json)
;;

let source_root options =
  match options.root, options.source with
  | Some a, Some b when not (String.equal (U.realpath (absolute a)) (U.realpath (absolute b))) ->
    bad "Conflicting --project-root and --source-root"
  | Some root, _ | _, Some root -> absolute root
  | None, None ->
    let cwd = U.realpath (U.getcwd ()) in
    if List.exists (String.split cwd ~on:'/') ~f:(fun part ->
      List.mem [ "_build"; "_flow_results"; ".dev" ] part ~equal:String.equal)
    then bad "Automatic root discovery is refused in generated trees; use --source-root";
    let rec find root =
      if is_file (Filename.concat root "dune-project")
         && is_file (Filename.concat root "asic-dependency.json") then root
      else let parent = Filename.dirname root in
        if String.equal parent root then bad "No project root found; use --source-root" else find parent in
    find cwd
;;

let selected options = Flow.Selection.create ?flow:options.flow ?profile:options.profile () |> checked
let endpoint options =
  Option.value_or_thunk options.endpoint ~default:(fun () -> bad "flow plan/emit requires --endpoint")
  |> Flow.Stage.of_string |> checked
;;

let flow_main command args =
  let allowed = common @ (match command with
    | "list" -> []
    | "describe" -> [ "--flow" ]
    | "plan" -> selection_options @ root_options
    | "emit" -> selection_options @ root_options @ [ "--results-root"; "--expected-plan-identity" ]
    | _ -> bad "Unknown flow subcommand") in
  let options = parse ("flow " ^ command) allowed args in
  let catalog = catalog () in
  match command with
  | "list" -> print options (Flow_spec.list_to_yojson catalog)
  | "describe" ->
    let id = Option.value_or_thunk options.flow ~default:(fun () -> bad "flow describe requires --flow ID") in
    let entry = List.find (Flow.Catalog.entries catalog) ~f:(fun entry ->
      String.equal id (Flow.Selection.Id.to_string (Flow.Methodology.id (Flow.Catalog.Entry.methodology entry))))
      |> Option.value_or_thunk ~default:(fun () -> bad "Unknown flow ID") in
    print options (Flow_spec.describe_to_yojson entry)
  | _ ->
    let selection = selected options and endpoint = endpoint options in
    let source_root = source_root options in
    let prepared = Methodology_plan.prepare ~catalog ~selection ~request:options.request ~endpoint
      ~catalog_inputs ?expected_plan_identity:options.expected (project ()) ~source_root |> checked in
    let plan = Methodology_plan.Prepared.plan prepared in
    if String.equal command "plan" then print options (Methodology_plan.to_yojson plan)
    else (
      let results = Option.value_map options.results ~f:absolute
        ~default:(Filename.concat source_root "_flow_results") in
      let bundle = Methodology_plan.Prepared.bundle prepared in
      let publication = Bundle.publish bundle ~store_dir:(Filename.concat results "bundles") |> checked in
      print options (`Assoc
        [ "schema_version", `Int 1; "kind", `String "bundle_emission"
        ; "bundle_identity", `String (Bundle.identity bundle)
        ; "plan_identity", `String (Methodology_plan.plan_identity plan)
        ; "output_dir", `String publication.directory; "reused", `Bool publication.reused
        ; "plan", Methodology_plan.to_yojson plan ]))
;;

let preparation_main command args =
  let options = parse command
    (common @ (if String.equal command "describe" then [] else root_options @ selection_options)
     @ if String.equal command "prepare" then [ "--results-root" ] else []) args in
  if String.equal command "describe" then (
    let project = project () in
    print options (`Assoc [ "project_name", `String (Project.name project)
      ; "declaration_sexp", `String (Sexp.to_string_hum (Project.describe project)) ]))
  else (
    let source_root = source_root options in
    let endpoint = Option.value options.endpoint ~default:"timing" |> Flow.Stage.of_string |> checked in
    let methodology = Flow.Catalog.resolve ~selection:(selected options) ~request:options.request
      (catalog ()) ~endpoint () |> checked in
    let prepare ~on_phase = Project.prepare_resources ~on_phase ~methodology ~catalog_inputs (project ()) ~source_root in
    if String.equal command "preview" then (
      match prepare ~on_phase:(fun _ -> ()) with
      | Ok result -> print options (Resource_preparation.to_json result)
      | Error failure -> print options (Resource_preparation.Failure.to_json failure); Stdlib.exit 1)
    else (
      let module E = Hardcaml_asic_execution in
      let request = E.Identity_json.parse (Yojson.Safe.to_string (`Assoc
        [ "project", `String "program_memory_specimen"; "source_root", `String source_root
        ; "methodology", Flow.Spec.resolved_to_yojson methodology ]))
        |> Result.map_error ~f:E.Identity_json.error_message |> Result.ok_or_failwith in
      let store = Option.value_map options.results ~f:absolute
        ~default:(Filename.concat source_root "_flow_results/preparation") in
      let outcome = E.Preparation_service.run_cli ~store ~request ~json:options.json ~prepare () in
      Stdlib.exit (Option.value outcome.record.exit_code ~default:1)))
;;

let () =
  try
    match Sys.get_argv () with
    | [|_; "prepare"; source_root; endpoint|] when not (String.is_prefix source_root ~prefix:"--") ->
      let endpoint = Flow.Stage.of_string endpoint |> Or_error.ok_exn in
      let _, _, preparation = prepare source_root endpoint in
      print_endline (Yojson.Safe.pretty_to_string preparation)
    | [|_; "export"; source_root; output_dir; endpoint|] ->
      let endpoint = Flow.Stage.of_string endpoint |> Or_error.ok_exn in
      (* This is the resource-preparation API used by consumer/Workbench preparation.
         It is evidence only, and neither publishes a bundle nor executes EDA. *)
      let project, catalog, preparation = prepare source_root endpoint in
      let prepared = Methodology_plan.prepare ~catalog ~endpoint
        ~catalog_inputs project ~source_root
        |> Or_error.ok_exn in
      let plan = Methodology_plan.Prepared.plan prepared in
      let decoded = Methodology_plan.to_yojson plan |> Methodology_plan.of_yojson |> Or_error.ok_exn in
      assert (String.equal (Methodology_plan.plan_identity plan) (Methodology_plan.plan_identity decoded));
      Bundle.write (Methodology_plan.Prepared.bundle prepared) ~output_dir |> Or_error.ok_exn;
      print_endline (Yojson.Safe.pretty_to_string (`Assoc
        [ "plan", Methodology_plan.to_yojson plan; "preparation", preparation
        ; "bundle", `String output_dir; "plan_identity", `String (Methodology_plan.plan_identity plan) ]))
    | _ ->
      (match Array.to_list (Sys.get_argv ()) with
       | [ _; "--help" ] -> print_endline usage
       | _ :: "flow" :: command :: args -> flow_main command args
       | _ :: ("prepare" | "preview" | "describe" as command) :: args -> preparation_main command args
       | _ -> bad "Unknown command")
  with exn ->
    match exn with
    | Stdlib.Arg.Help text -> print_string text
    | _ -> eprintf "%s\n%!" (Exn.to_string exn); Stdlib.exit 2
