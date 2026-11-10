open! Core
open Hardcaml_workbench_provider

let discovery : Wire.Discovery.t =
  { protocol_version = 1
  ; suites =
      [ { id = "controlled-fifo"
        ; label = "Controlled FIFO / independent list checker"
        ; cases =
            List.map [ "directed"; "seeded" ] ~f:(fun id : Wire.Case.t ->
              { id; label = "FIFO " ^ id })
        ; parameters =
            [ { key = "checker"
              ; label = "checker"
              ; default = "normal"
              ; choices = [ "normal"; "mismatch" ]
              }
            ; { key = "cycles"
              ; label = "cycles"
              ; default = "4096"
              ; choices = [ "64"; "4096"; "20000" ]
              }
            ]
        ; default_seed = "42"
        }
      ]
  }
;;

(* Decimal accumulation avoids signed-int conversion of a full uint64 seed. This is the
   project's historical FS2 PRNG mapping, not a wire encoding. *)
let seed_words seed =
  let words = Array.create ~len:4 0 in
  String.iter seed ~f:(fun digit ->
    let carry = ref (Char.to_int digit - Char.to_int '0') in
    Array.iteri words ~f:(fun i word ->
      let value = (word * 10) + !carry in
      words.(i) <- value land 65535;
      carry := value lsr 16));
  Array.to_list words |> List.map ~f:Int.to_string |> String.concat ~sep:","
;;

let validate_selection (selection : Wire.Selection.t) =
  if List.is_empty selection.asic_inputs
  then Ok ()
  else Or_error.error_string "FIFO simulation takes no ASIC inputs"
;;

let run simulator (context : Runner.context) =
  Or_error.try_with (fun () ->
    let selection = context.request.selection in
    let parameter key =
      List.Assoc.find_exn selection.parameters ~equal:String.equal key
    in
    let checker = parameter "checker" in
    let cycles = parameter "cycles" in
    let words = seed_words selection.seed in
    let parameters =
      List.map selection.parameters ~f:(fun (key, value) ->
        sprintf "'%s': '%s'" key value)
      |> String.concat ~sep:", "
    in
    let failed = ref false in
    let emit = context.emit in
    emit Started;
    List.iter selection.cases ~f:(fun case ->
      emit (Case_started case);
      printf
        "FIFO %s seed=%s words=%s parameters={%s}\n%!"
        case
        selection.seed
        words
        parameters;
      let status = ref None in
      let message = ref None in
      Runner.run_child
        ~prog:simulator
        ~args:
          [ case
          ; selection.seed
          ; words
          ; cycles
          ; Runner.artifact_path context (case ^ ".vcd")
          ; Runner.artifact_path context (case ^ ".sexp")
          ; checker
          ]
        ~on_stdout_line:(fun line ->
          if String.is_prefix line ~prefix:"PROGRESS "
          then (
            match
              String.split line ~on:' ' |> List.filter ~f:(Fn.non String.is_empty)
            with
            | [ _; completed; total ] ->
              emit
                (Progress
                   { case_id = Some case
                   ; completed = Int.of_string completed
                   ; total = Some (Int.of_string total)
                   ; unit_ = "FIFO edges"
                   })
            | _ -> failwith "invalid native progress")
          else if String.is_prefix line ~prefix:"CHECK_FAILED " && Option.is_none !message
          then (
            let summary =
              match String.substr_index line ~pattern:"(trace" with
              | None -> line
              | Some pos -> String.prefix line pos
            in
            message := Some (String.strip summary ^ " (see native report)"))
          else if String.is_prefix line ~prefix:"RESULT "
          then status := List.nth (String.split line ~on:' ') 1)
      |> Or_error.ok_exn;
      let case_status : Wire.Case_status.t =
        match !status with
        | Some "Passed" -> Passed
        | Some "Failed" ->
          failed := true;
          Failed
        | _ -> failwith "native simulator failed without a complete result"
      in
      let artifact suffix kind media_type =
        let path = case ^ suffix in
        emit
          (Artifact
             { id = path; case_id = Some case; label = path; kind; media_type; path })
      in
      artifact ".vcd" "waveform" "text/x-vcd";
      artifact
        ".sexp"
        (if Wire.Case_status.equal case_status Failed then "failure-report" else "report")
        "text/plain";
      emit (Case_finished { case_id = case; status = case_status; message = !message }));
    emit (Finished (if !failed then Failed else Passed)))
;;

let () =
  let argv = Sys.get_argv () in
  let simulator, argv =
    match Array.to_list argv with
    | program :: "--simulator" :: simulator :: rest ->
      simulator, Array.of_list (program :: rest)
    | _ ->
      Filename.concat (Filename.dirname Stdlib.Sys.executable_name) "fifo_sim.exe", argv
  in
  Runner.main ~argv ~discovery ~validate_selection ~run:(run simulator) ()
;;
