open! Core
open Hardcaml
open Fifo_test_support

module Dut = Controlled_fifo
module Sim = Cyclesim.With_interface (Dut.I) (Dut.O)

let run name traces =
  let sim = Sim.create Dut.create in
  let inputs = Cyclesim.inputs sim in
  let before = Cyclesim.outputs ~clock_edge:Before sim in
  let after = Cyclesim.outputs ~clock_edge:After sim in
  let pushes = ref 0 in
  let pops = ref 0 in
  let rejected_pushes = ref 0 in
  let rejected_pops = ref 0 in
  let resets = ref 0 in
  let stalls = ref 0 in
  let boundaries = Array.create ~len:17 0 in
  let history = ref [] in
  List.iteri traces ~f:(fun cycle (trace : Trace.t) ->
    let s = trace.stimulus in
    let drive port width value = port := Bits.of_int_trunc ~width value in
    let bit port value = drive port 1 (Bool.to_int value) in
    bit inputs.clear s.clear;
    bit inputs.enable s.enable;
    bit inputs.push s.push;
    bit inputs.pop s.pop;
    drive inputs.push_data 8 s.push_data;
    let check phase field port expected =
      let actual = Bits.to_int_trunc !port in
      if actual <> expected
      then
        raise_s
          [%message "FIFO mismatch"
            (name : string) (cycle : int) (phase : string) (field : string)
            (expected : int) (actual : int) (trace : Trace.t)
            (!history : Trace.t list)]
    in
    let check_bit phase field port value = check phase field port (Bool.to_int value) in
    let check_snapshot phase (ports : _ Dut.O.t) (expected : Snapshot.t) =
      check phase "occupancy" ports.occupancy expected.occupancy;
      check_bit phase "full" ports.full expected.full;
      check_bit phase "empty" ports.empty expected.empty;
      check phase "data_out" ports.data_out expected.data_out;
      check_bit phase "data_valid" ports.data_valid expected.data_valid
    in
    Cyclesim.cycle_check sim;
    Cyclesim.cycle_before_clock_edge sim;
    (* Initial state is not part of the hardware contract. First clear edge
       establishes it; its combinational accepts must still be suppressed. *)
    if cycle > 0 then check_snapshot "before" before trace.before;
    check_bit "before" "push_accept" before.push_accept trace.push_accept;
    check_bit "before" "pop_accept" before.pop_accept trace.pop_accept;
    Cyclesim.cycle_at_clock_edge sim;
    Cyclesim.cycle_after_clock_edge sim;
    check_snapshot "after" after trace.after;
    (* After-edge accepts describe the NEXT edge, not the operation just taken. *)
    if trace.push_accept then Int.incr pushes;
    if trace.pop_accept then Int.incr pops;
    if s.push && not trace.push_accept then Int.incr rejected_pushes;
    if s.pop && not trace.pop_accept then Int.incr rejected_pops;
    if s.clear then Int.incr resets;
    if not s.enable then Int.incr stalls;
    boundaries.(trace.before.occupancy) <- boundaries.(trace.before.occupancy) + 1;
    history := List.take (trace :: !history) 8);
  printf
    "PASS %s: edges=%d pushes=%d pops=%d rejected_pushes=%d rejected_pops=%d clears=%d disabled=%d pre_counts[0,1,15,16]=[%d,%d,%d,%d]\n%!"
    name (List.length traces) !pushes !pops !rejected_pushes !rejected_pops !resets !stalls
    boundaries.(0) boundaries.(1) boundaries.(15) boundaries.(16)
;;

let () =
  let directed = ref false in
  let seed = ref None in
  let cycles = ref None in
  let usage = "fifo_test --directed | --seed INT --cycles NONNEGATIVE_INT" in
  Stdlib.Arg.parse
    [ "--directed", Stdlib.Arg.Set directed, " Run directed scenarios"
    ; "--seed", Stdlib.Arg.Int (fun n -> seed := Some n), "INT Explicit regression seed"
    ; "--cycles", Stdlib.Arg.Int (fun n -> cycles := Some n), "INT Random traffic edges"
    ]
    (fun arg -> raise (Stdlib.Arg.Bad ("Unexpected argument: " ^ arg)))
    usage;
  match !directed, !seed, !cycles with
  | true, None, None -> run "directed" (Fifo_test_support.directed ())
  | false, Some seed, Some cycles when cycles >= 0 ->
    run (sprintf "seed=%d cycles=%d" seed cycles) (regression ~seed ~cycles)
  | _ ->
    eprintf "%s\n%!" usage;
    Stdlib.exit 2
;;
