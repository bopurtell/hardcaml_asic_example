(* hardcaml-asic profile directory v1 *)
open Hardcaml_asic

let create ~additional_profiles =
  let open Core.Or_error in
  bind (Flow.Methodology.create ~id:"funk_flow123" ~label:"Funk_flow123"
    ~description:"LibreLane physical-stage prefixes" ~backend_recipe:Librelane_classic_v1
    ~endpoints:[Synthesis; Floorplan; Placement; Cts; Routing; Timing; Signoff] ~configurable:Flow.Parameter.Key.all ~defaults:[]) ~f:(fun methodology ->
  bind (Flow.Profile.create ~id:"balanced" ~label:"Balanced" ~description:"" ~assignments:[]) ~f:(fun profile ->
  Flow.Catalog.Entry.create ~methodology ~profiles:(profile :: additional_profiles)
    ~default_profile:"balanced"))
