open! Core
open Hardcaml

module I = struct
  type 'a t =
    { clock : 'a
    ; clear : 'a
    ; enable : 'a
    ; push : 'a
    ; pop : 'a
    ; push_data : 'a [@bits 8]
    }
  [@@deriving hardcaml]
end

module O = struct
  type 'a t =
    { data_out : 'a [@bits 8]
    ; data_valid : 'a
    ; push_accept : 'a
    ; pop_accept : 'a
    ; occupancy : 'a [@bits 5]
    ; full : 'a
    ; empty : 'a
    }
  [@@deriving hardcaml]
end

let create (i : _ I.t) =
  let open Signal in
  let spec = Reg_spec.create ~clock:i.clock ~clear:i.clear () in
  let push_accept = wire 1 in
  let pop_accept = wire 1 in
  let read_pointer = reg_fb spec ~enable:pop_accept ~width:4 ~f:(fun p -> p +:. 1) in
  let write_pointer = reg_fb spec ~enable:push_accept ~width:4 ~f:(fun p -> p +:. 1) in
  let occupancy =
    reg_fb spec ~width:5 ~f:(fun count ->
      mux2 (push_accept ^: pop_accept) (mux2 push_accept (count +:. 1) (count -:. 1)) count)
  in
  let empty = occupancy ==:. 0 in
  let full = occupancy ==:. 16 in
  let active = i.enable &: ~:(i.clear) in
  pop_accept <-- (active &: i.pop &: ~:empty);
  push_accept <-- (active &: i.push &: (~:full |: pop_accept));
  (* Separate registers deliberately avoid RAM read-during-write semantics.
     The response register samples the old head on a full replacement edge. *)
  let storage_spec = Reg_spec.create ~clock:i.clock () in
  let words =
    List.init 16 ~f:(fun address ->
      reg storage_spec ~enable:(push_accept &: (write_pointer ==:. address)) i.push_data)
  in
  { O.data_out = reg spec ~enable:pop_accept (mux read_pointer words)
  ; data_valid = reg spec pop_accept
  ; push_accept
  ; pop_accept
  ; occupancy
  ; full
  ; empty
  }
;;
