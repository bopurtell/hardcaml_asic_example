open Hardcaml
open Hardcaml_asic

module I = Tt_cmos5l.I
module O = Tt_cmos5l.O

let name = "tt_um_controlled_fifo"

let create (i : _ I.t) =
  let open Signal in
  let fifo =
    Controlled_fifo.create
      { clock = i.clk
      ; clear = ~:(i.rst_n)
      ; enable = i.ena
      ; push = bit i.uio_in ~pos:0
      ; pop = bit i.uio_in ~pos:1
      ; push_data = i.ui_in
      }
  in
  let gate = Tt_cmos5l.gate ~enable:(i.ena &: i.rst_n) in
  { O.uo_out = gate fifo.data_out
  ; uio_out = gate (concat_msb [ fifo.occupancy; fifo.data_valid; zero 2 ])
  ; uio_oe = gate (of_int_trunc ~width:8 0xfc)
  }
;;
