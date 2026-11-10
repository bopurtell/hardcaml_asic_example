open! Core
open Hardcaml_asic

let ok = Or_error.ok_exn
let rejects value = assert (Or_error.is_error value)

let () =
  let catalog = Fifo_asic.Flow_catalog.create () |> ok in
  let resolve ?selection () = Flow.Catalog.resolve ?selection catalog ~endpoint:Synthesis () |> ok in
  let default = resolve () in
  assert (String.equal (Flow.Selection.Id.to_string (Flow.Profile.id (Flow.Catalog.profile default))) "balanced");
  let entry = Flow.Catalog.entry default in
  let methodology = Flow.Catalog.Entry.methodology entry in
  let profiles = Flow.Catalog.Entry.profiles entry in
  rejects (Flow.Catalog.create ~entries:[ entry ] ~default_flow:"missing" ~default_profile:"balanced");
  rejects (Flow.Catalog.create ~entries:[ entry ] ~default_flow:"standard" ~default_profile:"missing");
  rejects (Flow.Catalog.create ~entries:[ entry; entry ] ~default_flow:"standard" ~default_profile:"balanced");
  rejects (Flow.Catalog.Entry.create ~methodology ~profiles ~default_profile:"missing");
  rejects (Flow.Catalog.Entry.create ~methodology ~profiles:(profiles @ profiles) ~default_profile:"balanced");
  rejects (Flow.Profile.create ~id:"bad" ~label:"Bad" ~description:""
    ~assignments:[ Flow.Parameter.synth_abc_buffering false; Flow.Parameter.synth_abc_buffering false ]);
  rejects (Flow.Methodology.create ~id:"bad" ~label:"Bad" ~description:""
    ~backend_recipe:Librelane_classic_v1 ~endpoints:[ Synthesis ] ~configurable:[]
    ~defaults:[ Flow.Parameter.synth_abc_buffering false ]);
  (* Exercise the public default distinction with the actual project's checked entry. *)
  let alternative = Flow.Catalog.create ~entries:[ entry ] ~default_flow:"standard" ~default_profile:"synth_delay" |> ok in
  let selected selection = Flow.Catalog.resolve ~selection alternative ~endpoint:Synthesis () |> ok
    |> Flow.Catalog.profile |> Flow.Profile.id |> Flow.Selection.Id.to_string in
  assert (String.equal (selected Flow.Selection.default) "synth_delay");
  assert (String.equal (selected (Flow.Selection.create ~flow:"standard" () |> ok)) "balanced");
  rejects (Flow.Selection.create ~profile:"balanced" ());
  (* Discovery wires are provider contracts, and decode back into checked values. *)
  ignore (Flow_spec.list_of_yojson (Flow_spec.list_to_yojson catalog) |> ok : Flow.Catalog.t);
  ignore (Flow_spec.describe_of_yojson (Flow_spec.describe_to_yojson entry) |> ok : Flow.Catalog.Entry.t);
  printf "PASS project catalog: facade, discovery roundtrips, explicit defaults/selection, duplicate and invalid declaration rejection\n%!"
;;
