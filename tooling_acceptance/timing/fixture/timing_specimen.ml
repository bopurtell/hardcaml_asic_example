open Hardcaml

module I = struct
  type 'a t =
    { clk : 'a
    ; rst_n : 'a
    ; asynchronous : 'a
    ; synchronous : 'a
    }
  [@@deriving hardcaml]
end

module O = struct
  type 'a t =
    { captured : 'a
    ; control : 'a
    }
  [@@deriving hardcaml]
end

(* [anchor] is the integration seam for the provider's public register-anchor API.
   It receives the actual scalar register Q, before any output aliasing. It must
   return that register, with provider-owned naming/preservation attached. *)
let create ~anchor (i : _ I.t) =
  let open Signal in
  let spec = Reg_spec.create ~clock:i.clk ~reset:i.rst_n ~reset_level:Low () in
  let stage name d = anchor name (reg spec d) in
  let first = stage "capture_first" i.asynchronous in
  let second = stage "capture_second" first in
  let third = stage "capture_third" second in
  let control_first = stage "control_first" i.synchronous in
  let control = stage "control_second" control_first in
  { O.captured = third; control }
;;
