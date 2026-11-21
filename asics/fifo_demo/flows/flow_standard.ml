(* hardcaml-asic profile directory v1 *)
open! Core
open Hardcaml_asic

let create ~additional_profiles =
  let open Or_error.Let_syntax in
  let%bind methodology =
    Flow.Methodology.create ~id:"standard" ~label:"Standard"
      ~description:"Fresh LibreLane classic physical-stage prefixes"
      ~backend_recipe:Librelane_classic_v1 ~endpoints:Flow.Stage.all
      ~configurable:Flow.Parameter.Key.all ~defaults:[]
  in
  let%bind profiles = Standard_profiles.create () in
  Flow.Catalog.Entry.create ~methodology ~profiles:(profiles @ additional_profiles) ~default_profile:"balanced"
;;
