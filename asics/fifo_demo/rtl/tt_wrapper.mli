open Hardcaml

module I = Hardcaml_asic.Tt_cmos5l.I
module O = Hardcaml_asic.Tt_cmos5l.O

val name : string

(** Inputs, including reset, must be synchronous and stable across the rising edge.
    [not rst_n] clears the FIFO synchronously; there is no reset synchronizer.
    All outputs are masked immediately unless [ena && rst_n]. This mask does
    not reset queue state. UIO inputs 0/1 request push/pop; upper inputs are ignored.
    UIO outputs 7:3 are occupancy (bit 3 LSB), bit 2 response valid, 1:0 zero.
    Output enables are 0xFC while unmasked, zero otherwise. *)
val create : Signal.t I.t -> Signal.t O.t
