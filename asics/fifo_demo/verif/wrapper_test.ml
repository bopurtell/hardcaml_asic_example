open! Core
open Hardcaml
open Fifo_test_support

module Dut = Fifo_asic.Tt_wrapper
module Sim = Cyclesim.With_interface (Dut.I) (Dut.O)

let run name traces =
  let sim = Sim.create Dut.create in
  let i = Cyclesim.inputs sim in
  let before = Cyclesim.outputs ~clock_edge:Before sim in
  let after = Cyclesim.outputs ~clock_edge:After sim in
  let drive port width value = port := Bits.of_int_trunc ~width value in
  let controls ~enable ~clear =
    drive i.ena 1 (Bool.to_int enable);
    drive i.rst_n 1 (Bool.to_int (not clear))
  in
  List.iteri traces ~f:(fun cycle (trace : Trace.t) ->
    let s = trace.stimulus in
    let requests = Bool.to_int s.push lor (Bool.to_int s.pop lsl 1) in
    drive i.ui_in 8 s.push_data;
    let check phase (ports : _ Dut.O.t) (state : Snapshot.t) active =
      let field label port expected =
        let actual = Bits.to_int_trunc !port in
        if actual <> expected
        then raise_s [%message "TT wrapper mismatch"
          (name : string) (cycle : int) (phase : string) (label : string)
          (expected : int) (actual : int) (trace : Trace.t)]
      in
      field "uo_out" ports.uo_out (if active then state.data_out else 0);
      field "uio_out" ports.uio_out
        (if active then (state.occupancy lsl 3) lor (Bool.to_int state.data_valid lsl 2) else 0);
      field "uio_oe" ports.uio_oe (if active then 0xfc else 0)
    in
    let settle () =
      Cyclesim.cycle_check sim;
      Cyclesim.cycle_before_clock_edge sim
    in
    (* No edge in these probes: reset assertion masks immediately, release must
       reveal the SAME queue/response. Disabled probes likewise cannot clear it.
       Complementary upper input patterns check that those bits have no effect. *)
    let probe phase state =
      List.iter [ false, false; false, true; true, true; true, false ]
        ~f:(fun (enable, clear) ->
          controls ~enable ~clear;
          List.iter [ 0; 0xfc ] ~f:(fun upper ->
            drive i.uio_in 8 (requests lor upper);
            settle ();
            check phase before state (enable && not clear)))
    in
    if cycle > 0 then probe "pre-edge mask/reveal" trace.before;
    controls ~enable:s.enable ~clear:s.clear;
    (* Vary ignored bits at actual edges as well as during combinational probes. *)
    drive i.uio_in 8 (requests lor ((cycle land 63) lsl 2));
    settle ();
    if cycle > 0 || s.clear || not s.enable
    then check "before" before trace.before (s.enable && not s.clear);
    Cyclesim.cycle_at_clock_edge sim;
    Cyclesim.cycle_after_clock_edge sim;
    check "after" after trace.after (s.enable && not s.clear);
    probe "post-edge mask/reveal" trace.after);
  printf "PASS wrapper %s: edges=%d (pre/post-edge mask, reveal, OE and ignored-input probes)\n%!"
    name (List.length traces)
;;

let () =
  run "directed" (directed ());
  run "seed=20261012 cycles=20000" (regression ~seed:20261012 ~cycles:20000)
;;
