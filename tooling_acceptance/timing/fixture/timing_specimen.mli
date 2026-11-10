open Hardcaml

module I : sig
  type 'a t =
    { clk : 'a
    ; rst_n : 'a
    ; asynchronous : 'a
    ; synchronous : 'a
    }
  [@@deriving hardcaml]
end

module O : sig
  type 'a t =
    { captured : 'a
    ; control : 'a
    }
  [@@deriving hardcaml]
end

(** Three scalar capture stages and a separate two-stage synchronous control chain.
    Reset is active-low asynchronous on all five registers. This is a bounded
    timing specimen, not a CDC or reset-protocol qualification. *)
val create
  :  anchor:(string -> Signal.t -> Signal.t)
  -> Signal.t I.t
  -> Signal.t O.t
