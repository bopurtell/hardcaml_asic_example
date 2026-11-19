open! Core
open Hardcaml
open Fifo_test_support

module Dut = Controlled_fifo
module Sim = Cyclesim.With_interface (Dut.I) (Dut.O)

(* Checker phases/fields deliberately follow test/fifo_test.ml. The injected
   mismatch changes one checker expectation only; DUT and stimuli are untouched. *)
let () =
  let args = Sys.get_argv () in
  if Array.length args <> 8 then failwith "fifo_sim CASE SEED WORDS CYCLES VCD REPORT CHECKER";
  let case = args.(1) in
  let words = String.split args.(3) ~on:',' |> List.map ~f:Int.of_string |> Array.of_list in
  let cycles = Int.of_string args.(4) in
  (* The explicit export-stress case interprets this argument as a byte-size
     selection, rather than expanding the normal regression's in-memory list. *)
  let target_bytes =
    if String.equal case "export-stress"
    then (
      if not (List.mem [ 1; 16; 64 ] cycles ~equal:Int.equal)
      then failwith "export-stress size must be 1, 16 or 64 MiB";
      Some (cycles * 1024 * 1024))
    else None
  in
  let inject = String.equal args.(7) "mismatch" in
  if not (List.mem [ "normal"; "mismatch" ] args.(7) ~equal:String.equal)
  then failwith "unknown checker mode";
  let traces =
    match case with
    | "directed" -> directed ()
    | "seeded" -> regression_with_seed_words ~seed_label:args.(2) ~seed_words:words ~cycles
    | "export-stress" -> []
    | _ -> failwith "unknown case"
  in
  let vcd = Out_channel.create args.(5) in
  let sim = Vcd.wrap vcd (Sim.create Dut.create) in
  let inputs = Cyclesim.inputs sim in
  let before = Cyclesim.outputs ~clock_edge:Before sim in
  let after = Cyclesim.outputs ~clock_edge:After sim in
  let failures = ref [] in
  let checks = ref 0 in
  let history = ref [] in
  let total = Option.value target_bytes ~default:(List.length traces) in
  let edges = ref 0 in
  printf "PROGRESS 0 %d\n%!" total;
  let step cycle (trace : Trace.t) =
    let s = trace.stimulus in
    let drive port width value = port := Bits.of_int_trunc ~width value in
    let bit port value = drive port 1 (Bool.to_int value) in
    bit inputs.clear s.clear;
    bit inputs.enable s.enable;
    bit inputs.push s.push;
    bit inputs.pop s.pop;
    drive inputs.push_data 8 s.push_data;
    let check phase field port model_expected =
      Int.incr checks;
      let actual = Bits.to_int_trunc !port in
      let injected = inject && cycle = 17 && String.equal phase "after" && String.equal field "occupancy" in
      let expected = if injected then model_expected lxor 1 else model_expected in
      if actual <> expected then (
        let failure = [%message "FIFO mismatch" (cycle : int) (phase : string) (field : string)
          (expected : int) (actual : int) (model_expected : int) (injected : bool)
          (trace : Trace.t) (!history : Trace.t list)] in
        failures := failure :: !failures;
        printf "CHECK_FAILED %s\n%!" (Sexp.to_string failure))
    in
    let check_bit phase field port value = check phase field port (Bool.to_int value) in
    let snapshot phase (ports : _ Dut.O.t) (expected : Snapshot.t) =
      check phase "occupancy" ports.occupancy expected.occupancy;
      check_bit phase "full" ports.full expected.full;
      check_bit phase "empty" ports.empty expected.empty;
      check phase "data_out" ports.data_out expected.data_out;
      check_bit phase "data_valid" ports.data_valid expected.data_valid
    in
    Cyclesim.cycle_check sim;
    Cyclesim.cycle_before_clock_edge sim;
    if cycle > 0 then snapshot "before" before trace.before;
    check_bit "before" "push_accept" before.push_accept trace.push_accept;
    check_bit "before" "pop_accept" before.pop_accept trace.pop_accept;
    Cyclesim.cycle_at_clock_edge sim;
    Cyclesim.cycle_after_clock_edge sim;
    snapshot "after" after trace.after;
    history := List.take (trace :: !history) 8;
    Int.incr edges;
    let completed =
      match target_bytes with
      | None -> cycle + 1
      | Some _ -> Stdlib.pos_out vcd
    in
    let interval = if Option.is_some target_bytes then 65536 else 256 in
    if (cycle + 1) % interval = 0 || completed = total
    then printf "PROGRESS %d %d\n%!" completed total
  in
  (match target_bytes with
   | None -> List.iteri traces ~f:step
   | Some target ->
     let random = Stdlib.Random.State.make words in
     let model = ref Model.initial in
     (* Stream real Cyclesim transitions with the same independent checker. Keep
        only the current model and eight diagnostic edges, regardless of size. *)
     while Stdlib.pos_out vcd < target - 4096 do
       let stimulus =
         Stimulus.create
           ~clear:(!edges = 0)
           ~push:(!edges mod 64 < 48)
           ~pop:(!edges mod 64 >= 16)
           ~push_data:(Stdlib.Random.State.int random 256)
           ()
       in
       let next, trace = Trace.transition !model ("export-stress", stimulus) in
       model := next;
       step !edges trace
     done;
     (* Finish at an exact transport boundary without truncating a VCD event.
        At most 4 KiB is legal comment padding; the rest is simulated activity. *)
     let prefix = "$comment WB-040 exact-size padding " in
     let suffix = " $end\n" in
     let padding = target - Stdlib.pos_out vcd - String.length prefix - String.length suffix in
     if padding < 0 || padding > 4096 then failwith "VCD size reserve exhausted";
     Out_channel.output_string vcd (prefix ^ String.make padding ' ' ^ suffix);
     printf "PROGRESS %d %d\n%!" target target);
  Out_channel.close vcd;
  let status = if List.is_empty !failures then "Passed" else "Failed" in
  let seed = args.(2) in
  let checker = args.(7) in
  Out_channel.write_all args.(6) ~data:(Sexp.to_string_hum
    [%message "FIFO report" (case : string) (seed : string) (words : int array) (cycles : int)
      (checker : string) (status : string) (total : int) (target_bytes : int option)
      (!edges : int) (!checks : int)
      (List.rev !failures : Sexp.t list)] ^ "\n");
  printf "RESULT %s checks=%d edges=%d seed=%s\n%!" status !checks !edges seed
;;
