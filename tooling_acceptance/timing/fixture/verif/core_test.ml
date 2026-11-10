open Hardcaml

module Sim = Cyclesim.With_interface (Timing_specimen.I) (Timing_specimen.O)

let () =
  let anchors = ref [] in
  let sim =
    Sim.create
      (Timing_specimen.create ~anchor:(fun name q ->
         assert (Signal.width q = 1);
         (match q with
          | Signal.Type.Reg { register = { reset = Some reset; clear = None; enable = None; _ }; _ } ->
            assert (reset.reset_level = Low);
            assert (Signal.to_int_trunc reset.reset_to = 0)
          | _ -> failwith "expected a plain asynchronous-reset scalar register");
         anchors := name :: !anchors;
         q))
  in
  assert
    (List.rev !anchors
     = [ "capture_first"; "capture_second"; "capture_third"; "control_first"; "control_second" ]);
  let i = Cyclesim.inputs sim in
  let o = Cyclesim.outputs ~clock_edge:After sim in
  let drive port value = port := Bits.of_int_trunc ~width:1 value in
  let check label captured control =
    if Bits.to_int_trunc !(o.captured) <> captured
       || Bits.to_int_trunc !(o.control) <> control
    then failwith ("wrong pipeline result: " ^ label)
  in
  let cycle reset asynchronous synchronous =
    drive i.rst_n reset;
    drive i.asynchronous asynchronous;
    drive i.synchronous synchronous;
    Cyclesim.cycle sim
  in
  (* Cyclesim uses its reset operation, not asynchronous input transitions.
     Polarity/control structure is checked on the actual register nodes above. *)
  Cyclesim.reset sim;
  cycle 1 0 0;
  check "reset" 0 0;
  cycle 1 1 1;
  check "edge one" 0 0;
  cycle 1 0 0;
  check "edge two" 0 1;
  cycle 1 0 0;
  check "edge three" 1 0;
  cycle 1 0 0;
  check "edge four" 0 0;
  cycle 1 1 1;
  cycle 1 1 1;
  cycle 1 1 1;
  check "filled" 1 1;
  Cyclesim.reset sim;
  cycle 1 0 0;
  check "reset filled pipeline" 0 0;
  print_endline "PASS: five scalar async-reset register nodes (active-low, reset-to-zero), three/two-stage latency, Cyclesim reset"
