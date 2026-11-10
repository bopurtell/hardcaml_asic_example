open! Core

(** Plain values, independent of Hardcaml and any DUT interface. *)
module Stimulus : sig
  type t =
    { clear : bool
    ; enable : bool
    ; push : bool
    ; pop : bool
    ; push_data : int
    }
  [@@deriving sexp_of]

  val create
    :  ?clear:bool
    -> ?enable:bool
    -> ?push:bool
    -> ?pop:bool
    -> ?push_data:int
    -> unit
    -> t
end

module Snapshot : sig
  type t =
    { occupancy : int
    ; full : bool
    ; empty : bool
    ; data_out : int
    ; data_valid : bool
    }
  [@@deriving sexp_of]
end

module Model : sig
  (** Immutable ordered list model; no pointers or RTL acceptance helper. *)
  type t [@@deriving sexp_of]

  val initial : t
  val snapshot : t -> Snapshot.t

  (** Consume the old head first, then append if space remains. The empty case
      cannot consume the word appended on this edge. *)
  val step : t -> Stimulus.t -> t * bool * bool
  (** Result: next state, accepted push, accepted pop. *)
end

module Trace : sig
  type t =
    { label : string
    ; stimulus : Stimulus.t
    ; before : Snapshot.t
    ; push_accept : bool
    ; pop_accept : bool
    ; after : Snapshot.t
    }
  [@@deriving sexp_of]

  (** Evaluate stimuli from the reset state. Traces supplied by the generators
      begin with a synchronous clear edge and end with a drain/underflow edge. *)
  val of_stimuli : (string * Stimulus.t) list -> t list
end

val directed : unit -> Trace.t list

(** Exactly [cycles] random traffic edges, plus one initial clear and a final
    drain and rejected-pop edge. Local PRNG, reproducible for a fixed toolchain.
    Traffic alternates fill/drain bias, with boundary requests and reset stalls. *)
val regression : seed:int -> cycles:int -> Trace.t list

(** Same traffic/checker semantics, with explicit PRNG seed words. FS2 maps a
    canonical uint64 to four little-endian 16-bit words, preserving every bit. *)
val regression_with_seed_words
  :  seed_label:string
  -> seed_words:int array
  -> cycles:int
  -> Trace.t list
