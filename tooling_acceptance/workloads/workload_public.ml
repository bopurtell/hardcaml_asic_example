module E = Hardcaml_asic_execution
let () =
  let a = Sys.argv in
  let result = match a.(1) with
    | "directory-fds" ->
      let count () = Array.length (Sys.readdir "/proc/self/fd") in
      let reject () = match E.Workload_result.inspect a.(2) with
        | Error message -> message
        | Ok _ -> failwith "directory unexpectedly admitted" in
      let diagnostic = reject () in
      let before = count () in
      for _ = 1 to 500 do ignore (reject ()) done;
      let after = count () in
      if after <> before then Error "descriptor growth after rejected directory inspection"
      else Ok (`Assoc ["iterations", `Int 500; "fd_before", `Int before;
                       "fd_after", `Int after; "growth", `Int (after - before);
                       "diagnostic", `String diagnostic; "pid", `Int (Unix.getpid ())])
    | "inspect" -> E.Workload_result.inspect a.(2)
    | "recheck" -> (match E.Workload_result.recheck a.(2) ~expected_digest:a.(3) with
        | Ok () -> Ok (`Assoc ["recheck", `Bool true]) | Error _ as e -> e)
    | "targets" ->
      let optional s = if s = "-" then None else Some s in
      (match E.Variant_comparison.target ~kind:a.(2) ~path:a.(3),
             E.Variant_comparison.target ~kind:a.(4) ~path:a.(5) with
       | Ok left, Ok right -> E.Variant_comparison.inspect ~left ~right
           ?left_workload:(optional a.(6)) ?right_workload:(optional a.(7))
           ~axis:E.Variant_comparison.Resource_policy ()
       | Error e, _ | _, Error e -> Error e)
    | "compare" -> E.Variant_comparison.inspect
        ~left:(E.Variant_comparison.Bundle a.(2))
        ~right:(E.Variant_comparison.Bundle a.(3))
        ~left_workload:a.(4) ~right_workload:a.(5)
        ~axis:E.Variant_comparison.Resource_policy ()
    | _ -> Error "expected inspect|recheck|compare" in
  match result with
  | Ok value -> print_endline (E.Evidence_json.record_bytes value)
  | Error message -> prerr_endline message; exit 2
