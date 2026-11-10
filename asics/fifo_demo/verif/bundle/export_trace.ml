open! Core
open Fifo_test_support

let () =
  match Sys.get_argv () |> Array.to_list with
  | [ _; "--inputs" ] ->
    let project = Fifo_asic.project () |> Or_error.ok_exn in
    List.iter (Hardcaml_asic.Project.source_inputs project) ~f:(printf "%s\n")
  | [ _ ] ->
    List.iter [ directed (); regression ~seed:20261012 ~cycles:4096 ] ~f:(fun trace ->
      List.iteri trace ~f:(fun index (t : Trace.t) ->
        let s = t.stimulus in
        let pins (s : Snapshot.t) = (s.occupancy lsl 3) lor (Bool.to_int s.data_valid lsl 2) in
        printf "%d %d %d %d %d %d %d %d %d\n"
          (Bool.to_int (index > 0)) (Bool.to_int s.enable)
          (Bool.to_int (not s.clear)) s.push_data
          ((Bool.to_int s.push) lor (Bool.to_int s.pop lsl 1) lor ((index land 63) lsl 2))
          t.before.data_out (pins t.before) t.after.data_out (pins t.after)))
  | _ -> failwith "usage: export_trace.exe [--inputs]"
;;
