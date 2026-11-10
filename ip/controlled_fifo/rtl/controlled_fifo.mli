open! Core
open Hardcaml

(** Fixed 16-word x 8-bit register-backed FIFO, with 4-bit circular read/write
    pointers and 5-bit occupancy. No RAM primitive or fall-through bypass.

    At each rising edge, using pre-edge occupancy [count]:
    - [active = enable && not clear]
    - [pop_accept = active && pop && count > 0]
    - [push_accept = active && push && (count < 16 || pop_accept)]

    [clear] is synchronous, active high, and dominates [enable] and requests.
    It clears both pointers, occupancy, [data_out], and [data_valid]; stored
    words need not reset. Assert clear for an edge before using the FIFO.

    Empty simultaneous requests accept only the push (no bypass). Full
    simultaneous requests accept both and return the OLD head before replacing
    its storage slot. Other simultaneous accepted operations preserve occupancy
    and FIFO order. Disabled edges accept neither operation and hold the queue.

    [data_out] and [data_valid] are registered pop responses. Every non-clear
    edge sets [data_valid] to that edge's [pop_accept], holding [data_out] when
    no pop is accepted, including disabled edges. Consecutive pops may keep
    [data_valid] high; it is not a head-visible valid signal.

    Accept signals are combinational decisions for the upcoming edge. Occupancy,
    full and empty reflect current state even while clear is asserted before
    its edge; clear immediately suppresses both accepts. *)
module I : sig
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

module O : sig
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

val create : Signal.t I.t -> Signal.t O.t
