open! Core
open Hardcaml_asic

let emit root depth policy profile store ignored =
  let open Or_error.Let_syntax in
  let%bind checked = Variant_memory.variant (Int.of_string depth) in
  let requirement = match policy with
    | "flops" -> Resource_policy.Requirement.Flops
    | "exact" -> Exact | _ -> failwith "policy must be flops or exact" in
  let%bind project = Variant_memory.project ~ignore_depth:ignored checked requirement in
  let%bind catalog = Flow_catalog.create () in
  let%bind selection = Flow.Selection.create ~flow:"standard" ~profile () in
  let%bind methodology = Flow.Catalog.resolve ~selection catalog ~endpoint:Synthesis () in
  let%bind rendered = Project.render_result ~methodology
      ~catalog_inputs:Flow_catalog.source_inputs project ~source_root:root in
  let bundle = Project.Rendered.bundle rendered in
  let%map published = Bundle.publish bundle ~store_dir:store in
  `Assoc [ "bundle", `String published.directory
         ; "bundle_identity", `String (Bundle.identity bundle)
         ; "hardware_variant", Hardware_variant.to_yojson checked
         ; "flow", `String "standard"; "profile", `String profile ]
;;

let () =
  Printexc.record_backtrace true;
  let result =
    try
      match Array.to_list (Sys.get_argv ()) with
      | [ _; "emit"; root; depth; policy; profile; store ] ->
        emit root depth policy profile store false
      | [ _; "emit-ignored-negative"; root; depth; policy; profile; store ] ->
        emit root depth policy profile store true
      | [ _; "compare"; lk; left; rk; right; axis ] ->
        let module C = Hardcaml_asic_execution.Variant_comparison in
        let target kind path = match kind with
          | "bundle" -> C.Bundle path | "execution" -> C.Execution path
          | "coarse_run" -> C.Coarse_run path | _ -> failwith "invalid target kind" in
        let axis = match axis with
          | "hardware" -> C.Hardware | "resource_policy" -> C.Resource_policy
          | "flow_configuration" -> C.Flow_configuration | "descriptive" -> C.Descriptive
          | _ -> failwith "invalid axis" in
        C.inspect ~left:(target lk left) ~right:(target rk right) ~axis ()
        |> Result.map_error ~f:Error.of_string
      | _ -> Or_error.error_string
          "Usage: variant_cli emit ROOT DEPTH flops|exact PROFILE STORE | compare KIND PATH KIND PATH AXIS"
    with exn ->
      eprintf "%s\n%!" (Printexc.get_backtrace ());
      Or_error.of_exn exn
  in
  match result with
  | Ok value -> printf "%s\n%!" (Yojson.Safe.pretty_to_string value)
  | Error error -> eprintf "%s\n%!" (Error.to_string_hum error); Stdlib.exit 2
;;
