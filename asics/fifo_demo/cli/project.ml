module U = Unix
open! Core
open Hardcaml_asic

let usage = "Usage: project describe | prepare | preview | resources | emit | preflight | run [OPTIONS]\n       project flow list | describe | plan | emit | run [OPTIONS]"
let bad message = raise (Stdlib.Arg.Bad (message ^ "\n" ^ usage))
(* Executable paths must retain symlink-parent/.. traversal and venv aliases. *)
let anchor_executable path =
  if Filename.is_relative path then Filename.concat (U.getcwd ()) path else path
;;

let absolute path =
  (* Keep kernel traversal across symlink parents, including for missing outputs. *)
  anchor_executable path
;;

let is_file path = try match (U.stat path).st_kind with U.S_REG -> true | _ -> false with _ -> false
let generated path = List.exists (String.split path ~on:'/') ~f:(fun p ->
  List.mem [ "_build"; "_flow_results"; ".dev" ] p ~equal:String.equal)

let check_provider provider ~endpoint =
  let channel = U.open_process_args_in provider [|provider; "--version"; "--json"|] in
  let metadata = Exn.protect ~f:(fun () -> Yojson.Safe.from_channel channel)
    ~finally:(fun () -> match U.close_process_in channel with
       | U.WEXITED 0 -> () | _ -> failwith "Provider --version --json failed; CLI contract 2, 3 or 4 is required") in
  let open Yojson.Safe.Util in
   match metadata |> member "cli_contract" |> member "version" with
   | `Int 4 -> ()
   | `Int (2 | 3) when not endpoint -> ()
   | `Int (2 | 3) -> failwith "--endpoint requires CLI contract 4; refresh/activate a compatible provider"
   | _ -> failwith "Installed hardcaml-asic-flow requires supported CLI contract 2, 3 or 4; install/activate a compatible provider"
;;

let rec mkdir_p path =
  try U.mkdir path 0o755 with
  | U.Unix_error (U.EEXIST, _, _) ->
    if not (match (U.stat path).st_kind with U.S_DIR -> true | _ -> false)
    then bad ("Results parent is not a directory: " ^ path)
  | U.Unix_error (U.ENOENT, _, _) -> mkdir_p (Filename.dirname path); mkdir_p path
;;

let new_workspace results endpoint =
  mkdir_p results;
  let rec choose () =
    let name = Printf.sprintf "%s-%d-%08x%08x%08x%08x" endpoint (U.getpid ())
      (Stdlib.Random.bits ()) (Stdlib.Random.bits ()) (Stdlib.Random.bits ()) (Stdlib.Random.bits ()) in
    let path = Filename.concat results name in
    match U.lstat path with
    | _ -> choose ()
    | exception U.Unix_error (U.ENOENT, _, _) -> path
  in
  choose ()
;;

let discover () =
  let cwd = U.realpath (U.getcwd ()) in
  if generated cwd then bad "Automatic root discovery is refused in generated trees; use --project-root";
  let rec up path =
    if is_file (Filename.concat path "dune-project")
       && is_file (Filename.concat path "asic-dependency.json") then path
    else let parent = Filename.dirname path in
      if String.equal parent path then bad "No project root found; use --project-root or --source-root"
      else up parent
  in up cwd
;;

let find_provider explicit =
  match explicit with
  | Some path -> anchor_executable path
  | None ->
    let paths = String.split (Option.value (Sys.getenv "PATH") ~default:"") ~on:':' in
    (match List.find_map paths ~f:(fun dir ->
       let path = anchor_executable (Filename.concat (if String.is_empty dir then "." else dir) "hardcaml-asic-flow") in
       try U.access path [U.X_OK]; if is_file path then Some path else None with _ -> None) with
     | Some path -> path
     | None -> failwith "hardcaml-asic-flow is not on PATH; install/activate a compatible provider (CLI contract 2, 3 or 4).")
;;

let check_named_provider provider =
  let channel = U.open_process_args_in provider [| provider; "--version"; "--json" |] in
  let metadata = Exn.protect ~f:(fun () -> Yojson.Safe.from_channel channel)
    ~finally:(fun () -> match U.close_process_in channel with
      | U.WEXITED 0 -> () | _ -> failwith "Provider metadata failed; CLI4 + namedflow1 required") in
  (* Exact scalar types and unique fields, never truthiness or version coercion. *)
  let field key = function
    | `Assoc fields ->
      (match List.filter fields ~f:(fun (k, _) -> String.equal k key) with
       | [ (_, value) ] -> value
       | _ -> failwith "Malformed provider metadata; CLI4 + namedflow1 required")
    | _ -> failwith "Malformed provider metadata; CLI4 + namedflow1 required"
  in
  let contract = field "cli_contract" metadata in
  match field "version" contract, field "namedflow1" (field "capabilities" contract) with
  | `Int 4, `Bool true -> ()
  | _ -> failwith "Named flows require exact CLI4 + namedflow1=true; refresh a compatible provider"
;;

let immutable_plan_file path contents =
  (* Atomic no-replace visibility; this is the launch input, not an attempt receipt. *)
  let temporary = path ^ ".pending" in
  let fd = U.openfile temporary [ U.O_WRONLY; U.O_CREAT; U.O_EXCL ] 0o600 in
  let channel = U.out_channel_of_descr fd in
  Exn.protect ~f:(fun () ->
    Out_channel.output_string channel contents;
    Out_channel.close channel;
    U.chmod temporary 0o444;
    U.link temporary path)
    ~finally:(fun () -> Out_channel.close_no_err channel; U.unlink temporary)
;;

let flow_main command args =
  let json = ref false and verbose = ref false in
  let flow = ref None and profile = ref None and endpoint = ref None and expected = ref None in
  let source = ref None and root = ref None and results = ref None and provider = ref None in
  let tools = ref None and support = ref None and pdk = ref None and python = ref None in
  let timeout = ref None in
  let request = ref [] in
  let checked value = match value with Ok value -> value | Error error -> bad (Error.to_string_hum error) in
  let opt name dest help = name, Stdlib.Arg.String (fun s ->
    if String.is_empty s || String.is_prefix s ~prefix:"--" then bad (name ^ " requires a value");
    if Option.is_some !dest then bad ("Duplicate option " ^ name);
    dest := Some s), help in
  let set text =
    match String.lsplit2 text ~on:'=' with
    | None -> bad "--set requires KEY=VALUE"
    | Some (key, value) ->
      let key_type = Flow.Parameter.Key.of_string key |> checked |> Flow.Parameter.descriptor
        |> Flow.Parameter.value_type in
      let assignment = match key_type with
        | Enum -> Flow.Parameter.of_string_value ~key value |> checked
        | Boolean ->
          let scalar = try Yojson.Safe.from_string value with _ -> bad "--set boolean requires a JSON boolean scalar" in
          let scalar = match scalar with
            | `Bool b -> `Bool b
            | `Int n -> `Int n
            | `Float f -> `Float f
            | `Null -> `Null
            | `String s -> `String s
            | _ -> bad "--set requires a scalar" in
          Flow.Parameter.of_scalar ~key scalar |> checked
      in
      request := assignment :: !request
  in
  let common = [ "--json", Stdlib.Arg.Set json, " Versioned JSON output"
               ; "--verbose", Stdlib.Arg.Set verbose, " Diagnostics on stderr" ] in
  let selection = [ opt "--flow" flow "ID Flow ID"; opt "--profile" profile "ID Profile ID" ] in
  let preparation = selection @
    [ opt "--endpoint" endpoint "STAGE Required complete fresh prefix endpoint"
    ; "--set", Stdlib.Arg.String set, "KEY=VALUE Typed supported parameter override (repeatable)"
    ; opt "--source-root" source "PATH Source checkout"
    ; opt "--project-root" root "PATH Source checkout alias" ] in
  let options = common @ (match command with
    | "list" -> []
    | "describe" -> [ opt "--flow" flow "ID Required flow ID" ]
    | "plan" -> preparation
    | "emit" -> preparation @
      [ opt "--expected-plan-identity" expected "HASH Optional preview identity"
      ; opt "--results-root" results "PATH Results store (default SOURCE/_flow_results)" ]
    | "run" -> preparation @
      [ opt "--expected-plan-identity" expected "HASH Required preview identity"
      ; opt "--provider" provider "PATH Installed native provider executable"
      ; opt "--results-root" results "PATH Results store"
      ; opt "--toolchain" tools "PATH Tool root"
      ; opt "--support-tools" support "PATH Support tools"
       ; opt "--pdk-root" pdk "PATH PDK"
       ; "--timeout", Stdlib.Arg.String (fun s ->
           if Option.is_some !timeout then bad "Duplicate option --timeout";
           let seconds = try Int.of_string s with _ -> bad "--timeout requires positive integer seconds" in
           if seconds <= 0 then bad "--timeout requires positive integer seconds";
           timeout := Some (Int.to_string seconds)), "SECONDS Positive integer per segment/publication budget (provider default 600)"
       ; opt "--python" python "PATH Flow interpreter" ]
    | _ -> bad "Unknown flow subcommand") in
  Stdlib.Arg.parse_argv ~current:(ref 0) (Array.of_list (("project flow " ^ command) :: args))
    options (fun arg -> bad ("Unexpected argument: " ^ arg)) usage;
  let catalog = Fifo_asic.Flow_catalog.create () |> checked in
  let print value = printf "%s\n%!" (if !json then Yojson.Safe.to_string value else Yojson.Safe.pretty_to_string value) in
  match command with
  | "list" -> print (Flow_spec.list_to_yojson catalog)
  | "describe" ->
    let id = Option.value_or_thunk !flow ~default:(fun () -> bad "flow describe requires --flow ID") in
    let id = Flow.Selection.Id.create id |> checked in
    let entry = List.find (Flow.Catalog.entries catalog) ~f:(fun entry ->
      String.equal (Flow.Selection.Id.to_string id)
        (Flow.Selection.Id.to_string (Flow.Methodology.id (Flow.Catalog.Entry.methodology entry))))
      |> Option.value_or_thunk ~default:(fun () -> bad "Unknown flow ID") in
    print (Flow_spec.describe_to_yojson entry)
  | _ ->
    let selection = Flow.Selection.create ?flow:!flow ?profile:!profile () |> checked in
     let endpoint = Option.value_or_thunk !endpoint ~default:(fun () -> bad "flow plan/emit/run requires --endpoint")
      |> Flow.Stage.of_string |> checked in
    let request = Flow.Parameter.check_assignments ~configurable:Flow.Parameter.Key.all !request |> checked in
     if String.equal command "run" && Option.is_none !expected then
       bad "flow run requires --expected-plan-identity from flow plan";
     Option.iter !expected ~f:(fun identity ->
      if String.length identity <> 64 || not (String.for_all identity ~f:(function '0'..'9' | 'a'..'f' -> true | _ -> false))
      then bad "--expected-plan-identity requires a lowercase SHA-256");
    let explicit = match !root, !source with
      | Some a, Some b when not (String.equal (U.realpath (absolute a)) (U.realpath (absolute b))) -> bad "Conflicting --project-root and --source-root"
      | Some a, _ | _, Some a -> Some (absolute a) | _ -> None in
    let source_root = Option.value_or_thunk explicit ~default:discover in
    let project = Fifo_asic.project () |> Or_error.ok_exn in
    if Option.is_none explicit then List.iter (Project.source_inputs project) ~f:(fun input ->
      let path = Filename.concat source_root input in
      if not (is_file path) || not (String.is_prefix (U.realpath path) ~prefix:(source_root ^ "/"))
      then bad ("Discovered root lacks expected source input: " ^ input));
    let prepared = Methodology_plan.prepare ~catalog ~selection ~request ~endpoint
      ~catalog_inputs:Fifo_asic.Flow_catalog.source_inputs ?expected_plan_identity:!expected
      project ~source_root |> Or_error.ok_exn in
     let plan = Methodology_plan.Prepared.plan prepared in
     if String.equal command "plan" then print (Methodology_plan.to_yojson plan)
     else if String.equal command "emit" then (
       let results = Option.value_map !results ~default:(Filename.concat source_root "_flow_results") ~f:absolute in
       let bundle = Methodology_plan.Prepared.bundle prepared in
       let publication = Bundle.publish bundle
         ~store_dir:(Filename.concat results "bundles") |> Or_error.ok_exn in
       print (`Assoc
         [ "schema_version", `Int 1
         ; "kind", `String "bundle_emission"
         ; "bundle_identity", `String (Bundle.identity bundle)
         ; "plan_identity", `String (Methodology_plan.plan_identity plan)
         ; "output_dir", `String publication.directory
         ; "reused", `Bool publication.reused
         ; "plan", Methodology_plan.to_yojson plan ]))
     else (
      let provider = find_provider !provider in
      check_named_provider provider;
      let results = Option.value_map !results ~default:(Filename.concat source_root "_flow_results") ~f:absolute in
      let publication = Bundle.publish (Methodology_plan.Prepared.bundle prepared)
        ~store_dir:(Filename.concat results "bundles") |> Or_error.ok_exn in
      let workspace = new_workspace results (Flow.Stage.to_string endpoint) in
      let launchspecs = Filename.concat results "launchspecs" in
      mkdir_p launchspecs;
      let planfile = Filename.concat launchspecs (Filename.basename workspace ^ ".json") in
      immutable_plan_file planfile (Methodology_plan.to_string plan);
      let toolchain = Option.first_some !tools (Sys.getenv "TOOLCHAIN" |> Option.filter ~f:(fun s -> not (String.is_empty s)))
        |> Option.value_map ~default:(Filename.concat source_root "_flow_tools") ~f:absolute in
      let resolved override suffix = Option.value_map override ~default:(Filename.concat toolchain suffix) ~f:absolute in
      let argv = [ "stages"; publication.directory; "--methodology-plan"; planfile
        ; "--expected-plan-identity"; Methodology_plan.plan_identity plan
        ; "--workspace"; workspace; "--checkpoint-store"; Filename.concat workspace "checkpoints"
        ; "--support-tools"; resolved !support "tt"; "--pdk-root"; resolved !pdk "pdk"
        ; "--python"; Option.value_map !python ~default:(Filename.concat toolchain ".venv/bin/python") ~f:anchor_executable ]
        @ Option.value_map !timeout ~default:[] ~f:(fun s -> [ "--timeout"; s ])
        @ (if !json then [ "--json" ] else []) @ (if !verbose then [ "--verbose" ] else []) in
      U.execv provider (Array.of_list (provider :: argv)))
;;

let main command args =
  let json = ref false and verbose = ref false and native = ref false in
  let source = ref None and root = ref None and results = ref None and output = ref None in
  let bundle = ref None and tools = ref None and stage = ref None and runs = ref None in
  let endpoint = ref None in
  let simulation = ref false in
  let python = ref None and support = ref None and pdk = ref None in
  let opt name dest help = name, Stdlib.Arg.String (fun s ->
    if String.is_empty s || String.is_prefix s ~prefix:"--" then bad (name ^ " requires a nonempty path");
    dest := Some s), "PATH " ^ help in
  let common =
    [ "--json", Stdlib.Arg.Set json, " Machine-readable output"
    ; "--verbose", Stdlib.Arg.Set verbose, " Extra diagnostics on stderr" ] in
  let roots = [opt "--source-root" source "Source checkout"; opt "--project-root" root "Project root alias";
               opt "--results-root" results "Results root (default ROOT/_flow_results)"] in
  let routing = [opt "--bundle" bundle "Existing bundle"; opt "--toolchain" tools "Tool root";
    opt "--python" python "Python override"; opt "--support-tools" support "Support tools override";
    opt "--pdk-root" pdk "PDK override"; "--native", Stdlib.Arg.Set native, " Native execution"] in
  let options = match command with
    | "describe" -> common
    | "prepare" -> common @ roots
    | "preview" -> common @ [opt "--source-root" source "Source checkout";
                             opt "--project-root" root "Project root alias"]
    | "resources" -> common @
      [ "--simulation", Stdlib.Arg.Set simulation, " Explicit behavioral Simulation inventory" ]
    | "emit" -> common @ roots @ [opt "--output-dir" output "Exact new or empty bundle directory"]
    | "preflight" -> common @ roots @ routing @ [opt "--output" output "Exact report file"]
    | "run" -> common @ roots @ routing @
      [ "--stage", Stdlib.Arg.String (fun s -> stage := Some s), "synthesis|full Required implementation stage";
          "--endpoint", Stdlib.Arg.String (fun s -> endpoint := Some s), "synthesis|floorplan|placement|cts|routing|timing|signoff Explicit-stage endpoint (contract 4)";
         opt "--runs" runs "Classic run store override" ]
    | _ -> bad "Unknown command" in
  Stdlib.Arg.parse_argv ~current:(ref 0) (Array.of_list (("project " ^ command) :: args))
    options (fun arg -> bad ("Unexpected argument: " ^ arg)) usage;
  if String.equal command "run" then
     (match !stage, !endpoint with
      | Some _, Some _ -> bad "--stage and --endpoint are mutually exclusive"
       | None, Some ("synthesis" | "floorplan" | "placement" | "cts" | "routing" | "timing" | "signoff") ->
        if !native || Option.is_some !runs then bad "--endpoint does not support Classic-only --native or --runs"
      | Some ("synthesis" | "full"), None -> ()
       | _ -> bad "run requires --stage synthesis|full or --endpoint synthesis|floorplan|placement|cts|routing|timing|signoff");
  let explicit = match !root, !source with
    | Some a, Some b when not (String.equal (U.realpath (absolute a)) (U.realpath (absolute b))) -> bad "Conflicting --project-root and --source-root"
    | Some a, _ | _, Some a -> Some (absolute a) | _ -> None in
   if String.equal command "prepare" then (
     let source_root = Option.value_or_thunk explicit ~default:discover in
     let store = Option.value_map !results
       ~default:(Filename.concat source_root "_flow_results/preparation") ~f:absolute in
     let module E = Hardcaml_asic_execution in
     let request = E.Identity_json.parse (Yojson.Safe.to_string
       (`Assoc [ "project", `String "fifo"; "source_root", `String source_root ]))
       |> Result.map_error ~f:E.Identity_json.error_message |> Result.ok_or_failwith in
     let outcome = E.Preparation_service.run_cli ~store ~request ~json:!json
       ~prepare:(fun ~on_phase ->
         let project = Fifo_asic.project () |> Or_error.ok_exn in
         Project.prepare_resources ~on_phase project ~source_root) () in
     Stdlib.exit (Option.value outcome.record.exit_code ~default:1));
   let project = Fifo_asic.project () |> Or_error.ok_exn in
   if String.equal command "preview" then (
     let source_root = Option.value_or_thunk explicit ~default:discover in
     match Project.prepare_resources project ~source_root with
     | Ok prepared -> printf "%s%!" (Resource_preparation.to_string prepared); Stdlib.exit 0
     | Error failure ->
       printf "%s\n%!" (Yojson.Safe.pretty_to_string (Resource_preparation.Failure.to_json failure));
       Stdlib.exit 1);
   if String.equal command "resources" then (
     let view = if !simulation then
       Project.elaborate project ~mode:Simulation |> Or_error.ok_exn
       |> Resource_snapshot.of_elaborated
     else Project.elaborate_for_flow project |> Or_error.ok_exn |> Resource_snapshot.of_resolved in
     printf "%s\n%!" (Yojson.Safe.pretty_to_string (Resource_snapshot.to_json view));
     Stdlib.exit 0);
  if String.equal command "describe" then (
    let declaration = Sexp.to_string_hum (Project.describe project) in
    if !json then printf "%s\n%!" (Yojson.Safe.to_string (`Assoc
       [ "project_name", `String (Project.name project); "declaration_sexp", `String declaration ]))
    else printf "%s\n%!" declaration;
    if !verbose then eprintf "Local declaration; not a Workbench protocol payload.\n%!")
  else (
    let root = Option.value_or_thunk explicit ~default:discover in
    let results = Option.value_map !results ~default:(Filename.concat root "_flow_results") ~f:absolute in
    let provider = if List.mem ["preflight"; "run"] command ~equal:String.equal then (
      let paths = String.split (Option.value (Sys.getenv "PATH") ~default:"") ~on:':' in
      match List.find_map paths ~f:(fun dir ->
        let path = anchor_executable (Filename.concat (if String.is_empty dir then "." else dir) "hardcaml-asic-flow") in
        try U.access path [U.X_OK]; if is_file path then Some path else None with _ -> None) with
       | Some path -> check_provider path ~endpoint:(Option.is_some !endpoint); Some path
        | None -> failwith "hardcaml-asic-flow is not on PATH; install/activate a compatible provider (CLI contract 2, 3 or 4).") else None in
    let emit () =
      if Option.is_none explicit then List.iter (Project.source_inputs project) ~f:(fun input ->
        let path = Filename.concat root input in
        if not (is_file path) || not (String.is_prefix (U.realpath path) ~prefix:(root ^ "/"))
        then bad ("Discovered root lacks expected source input: " ^ input));
      match !output with
      | Some dir when String.equal command "emit" ->
        let dir = absolute dir in
        let b = Project.emit_bundle project ~source_root:root ~output_dir:dir |> Or_error.ok_exn in
        b, dir, false
      | _ ->
        let b, publication = Project.emit_bundle_to_store project ~source_root:root
          ~store_dir:(Filename.concat results "bundles") |> Or_error.ok_exn in
        b, publication.directory, publication.reused in
    if String.equal command "emit" then (
      let b, dir, reused = emit () in
      if !json then printf "%s\n%!" (Yojson.Safe.to_string (`Assoc
        [ "identity", `String (Bundle.identity b); "output_dir", `String dir ]))
      else printf "%s bundle %s\nIdentity: %s\n%!" (if reused then "Reused" else "Created") dir (Bundle.identity b);
      if !verbose then eprintf "Source root: %s\nResults root: %s\n%!" root results)
    else (
      let dir = match !bundle with Some path -> absolute path | None -> let _, dir, _ = emit () in dir in
      let toolchain = Option.first_some !tools (Sys.getenv "TOOLCHAIN" |> Option.filter ~f:(fun s -> not (String.is_empty s)))
        |> Option.value_map ~default:(Filename.concat root "_flow_tools") ~f:absolute in
       let argv = match !endpoint with
         | None -> [command; dir; "--results-root"; results; "--toolchain"; toolchain]
         | Some endpoint ->
           let workspace = new_workspace results endpoint in
           let resolved override suffix = Option.value_map override
             ~default:(Filename.concat toolchain suffix) ~f:absolute in
           ["stages"; dir; "--endpoint"; endpoint; "--workspace"; workspace;
            "--checkpoint-store"; Filename.concat workspace "checkpoints";
            "--support-tools"; resolved !support "tt"; "--pdk-root"; resolved !pdk "pdk";
            "--python"; Option.value_map !python ~default:(Filename.concat toolchain ".venv/bin/python") ~f:anchor_executable] in
       let overrides = if Option.is_some !endpoint then [] else
         ["--python", !python; "--support-tools", !support; "--pdk-root", !pdk;
          "--output", !output; "--runs", !runs] in
       let argv = List.fold overrides ~init:argv ~f:(fun a (flag, v) ->
           match v with None -> a | Some p ->
             let path = if String.equal flag "--python" then anchor_executable p else absolute p in
             a @ [flag; path]) in
      let argv = argv @ (Option.value_map !stage ~default:[] ~f:(fun s -> ["--stage"; s]))
        @ (if !native then ["--native"] else []) @ (if !json then ["--json"] else [])
        @ (if !verbose then ["--verbose"] else []) in
      let provider = Option.value_exn provider in
        if !verbose then eprintf "Dispatching installed provider %s (supports CLI contract 2, 3 or 4)\n%!" provider;
      U.execv provider (Array.of_list (provider :: argv))))
;;

let () =
   Stdlib.Random.self_init ();
  try match Sys.get_argv () |> Array.to_list with
    | [_; ("--help" | "-help")] -> printf "%s\n%!" usage
    | _ :: "flow" :: command :: args -> flow_main command args
    | [ _; "flow" ] -> bad "A flow subcommand is required"
    | _ :: command :: args -> main command args
    | _ -> bad "A subcommand is required"
  with
  | Stdlib.Arg.Bad message -> eprintf "%s\n%!" message; Stdlib.exit 2
  | Stdlib.Arg.Help message -> printf "%s%!" message
    | exn -> eprintf "project failed: %s\nUse a committed source checkout with the declared inputs and a compatible installed provider (CLI contract 2, 3 or 4).\n%!" (Exn.to_string exn); Stdlib.exit 1
