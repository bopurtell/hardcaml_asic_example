open! Core

module Stimulus = struct
  type t =
    { clear : bool
    ; enable : bool
    ; push : bool
    ; pop : bool
    ; push_data : int
    }
  [@@deriving sexp_of]

  let create ?(clear = false) ?(enable = true) ?(push = false) ?(pop = false)
    ?(push_data = 0) () =
    if push_data < 0 || push_data > 255 then invalid_arg "push_data must be a byte";
    { clear; enable; push; pop; push_data }
  ;;
end

module Snapshot = struct
  type t =
    { occupancy : int
    ; full : bool
    ; empty : bool
    ; data_out : int
    ; data_valid : bool
    }
  [@@deriving sexp_of]
end

module Model = struct
  type t =
    { contents : int list
    ; data_out : int
    ; data_valid : bool
    }
  [@@deriving sexp_of]

  let initial = { contents = []; data_out = 0; data_valid = false }

  let snapshot t =
    let occupancy = List.length t.contents in
    { Snapshot.occupancy
    ; full = occupancy = 16
    ; empty = occupancy = 0
    ; data_out = t.data_out
    ; data_valid = t.data_valid
    }
  ;;

  let step t (s : Stimulus.t) =
    if s.clear
    then initial, false, false
    else if not s.enable
    then { t with data_valid = false }, false, false
    else (
      let contents, data_out, popped =
        match s.pop, t.contents with
        | true, head :: rest -> rest, head, true
        | _ -> t.contents, t.data_out, false
      in
      let contents, pushed =
        if s.push && List.length contents < 16
        then contents @ [ s.push_data ], true
        else contents, false
      in
      { contents; data_out; data_valid = popped }, pushed, popped)
  ;;
end

module Trace = struct
  type t =
    { label : string
    ; stimulus : Stimulus.t
    ; before : Snapshot.t
    ; push_accept : bool
    ; pop_accept : bool
    ; after : Snapshot.t
    }
  [@@deriving sexp_of]

  let transition state (label, stimulus) =
    let next, push_accept, pop_accept = Model.step state stimulus in
    ( next
    , { label
      ; stimulus
      ; before = Model.snapshot state
      ; push_accept
      ; pop_accept
      ; after = Model.snapshot next
      } )
  ;;

  let of_stimuli stimuli = snd (List.fold_map stimuli ~init:Model.initial ~f:transition)
end

(* Small generator helper; only the public pure Model/Trace types are needed by
   another simulator adapter. *)
let generate f =
  let state = ref Model.initial in
  let traces = ref [] in
  let emit label stimulus =
    let next, trace = Trace.transition !state (label, stimulus) in
    state := next;
    traces := trace :: !traces
  in
  let occupancy () = (Model.snapshot !state).occupancy in
  emit "initial-clear" (Stimulus.create ~clear:true ());
  f emit occupancy;
  for _ = 1 to occupancy () do
    emit "final-drain" (Stimulus.create ~pop:true ())
  done;
  emit "final-underflow" (Stimulus.create ~pop:true ());
  List.rev !traces
;;

let directed () =
  let s = Stimulus.create in
  generate (fun emit _ ->
    (* Each probe begins at exactly the requested occupancy, with a nonzero
       previous response, so resets/holds also check response state. *)
    List.iter [ 0; 1; 15; 16 ] ~f:(fun count ->
      List.iter [ false; true ] ~f:(fun clear ->
        List.iter [ false; true ] ~f:(fun enable ->
          List.iter [ false; true ] ~f:(fun push ->
            List.iter [ false; true ] ~f:(fun pop ->
              let label =
                sprintf "matrix/count=%d/clear=%b/enable=%b/push=%b/pop=%b"
                  count clear enable push pop
              in
              emit (label ^ "/reset") (s ~clear:true ());
              emit (label ^ "/prime") (s ~push:true ~push_data:213 ());
              emit (label ^ "/response") (s ~pop:true ());
              for data = 1 to count do
                emit (label ^ "/fill") (s ~push:true ~push_data:data ())
              done;
              emit label (s ~clear ~enable ~push ~pop ~push_data:239 ());
              for _ = 1 to 17 do
                emit (label ^ "/drain") (s ~pop:true ())
              done)))));
    emit "empty-no-bypass/reset" (s ~clear:true ());
    emit "empty-no-bypass" (s ~push:true ~pop:true ~push_data:171 ());
    emit "response" (s ~pop:true ());
    emit "disabled-clears-valid" (s ~enable:false ~push:true ~pop:true ());
    emit "idle-holds-data" (s ());
    emit "underflow-holds-data" (s ~pop:true ());
    for data = 1 to 16 do
      emit "full-response/fill" (s ~push:true ~push_data:data ())
    done;
    emit "full-response/replace" (s ~push:true ~pop:true ~push_data:254 ());
    emit "full-response/disabled" (s ~enable:false ~push:true ~pop:true ());
    emit "full-response/replace-again" (s ~push:true ~pop:true ~push_data:255 ());
    emit "full-response/disabled-clear"
      (s ~clear:true ~enable:false ~push:true ~pop:true ());
    (* Includes full old-head replacement, near-full and singleton streams,
       many wraps, consecutive valid responses and post-stream order checks. *)
    List.iter [ 1; 15; 16 ] ~f:(fun count ->
      emit "stream/reset" (s ~clear:true ());
      for data = 0 to count - 1 do
        emit "stream/fill" (s ~push:true ~push_data:data ())
      done;
      for cycle = 0 to 1023 do
        emit (sprintf "stream/count=%d/cycle=%d" count cycle)
          (s ~push:true ~pop:true ~push_data:((cycle * 73 + 29) land 255) ())
      done;
      for _ = 1 to count + 1 do
        emit "stream/drain" (s ~pop:true ())
      done);
    for round = 0 to 63 do
      for offset = 0 to 17 do
        emit "wrap/fill-overflow" (s ~push:true ~push_data:((round + offset) land 255) ())
      done;
      for _ = 0 to 17 do
        emit "wrap/drain-underflow" (s ~pop:true ())
      done
    done)
;;

let regression_with_seed_words ~seed_label ~seed_words ~cycles =
  if cycles < 0 then invalid_arg "cycles must be nonnegative";
  let random = Stdlib.Random.State.make seed_words in
  let chance n = Stdlib.Random.State.int random 100 < n in
  generate (fun emit occupancy ->
    for cycle = 0 to cycles - 1 do
      let fill = cycle / 64 mod 2 = 0 in
      let push, pop =
        match occupancy () with
        | 0 | 1 | 15 | 16 when chance 40 -> true, true
        | _ ->
          let push = chance (if fill then 90 else 25) in
          let pop = chance (if fill then 25 else 90) in
          push, pop
      in
      let clear = chance 1 in
      let enable = chance 90 in
      let push_data = Stdlib.Random.State.int random 256 in
      emit (sprintf "seed=%s/random-cycle=%d" seed_label cycle)
        (Stimulus.create ~clear ~enable ~push ~pop ~push_data ())
    done)
;;

let regression ~seed ~cycles =
  regression_with_seed_words ~seed_label:(Int.to_string seed) ~seed_words:[| seed |] ~cycles
;;
