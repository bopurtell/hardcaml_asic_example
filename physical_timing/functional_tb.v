`timescale 1ns/1ps
// Deterministic digital functional replay only. Inputs change at falling edges;
// this test does not model metastability or approve asynchronous reset release.
module timing_physical_replay;
  reg clk = 0;
  always #10 clk = ~clk;
  reg ena = 0, rst_n = 0;
  reg [7:0] ui_in = 0, uio_in = 0;
  wire [7:0] uo_out, uio_out, uio_oe;
  tt_um_pt7_timing dut (.*);
  reg [2:0] capture = 0;
  reg [1:0] control = 0;
  reg [7:0] expected;
  integer n, checks = 0;
  reg negative;

  task check;
    begin
      expected = {6'b0, control[1] & ui_in[2], capture[2] & ui_in[2]};
      if (negative && checks == 20) expected = expected ^ 1;
      if (uo_out !== expected || uio_out !== 0 || uio_oe !== 0)
        $fatal(1, "functional mismatch check=%0d expected=%h got=%h uio=%h oe=%h",
               checks, expected, uo_out, uio_out, uio_oe);
      checks = checks + 1;
    end
  endtask

  initial begin
    negative = $test$plusargs("negative");
    for (n = 0; n < 256; n = n + 1) begin
      @(negedge clk);
      rst_n = !(n < 3 || n == 40 || n == 41 || n == 170);
      ena = ((n * 13 + n / 7) & 1);
      ui_in = ((n * 73) ^ (n >> 2));
      uio_in = ~ui_in;
      if (!rst_n) begin capture = 0; control = 0; end
      #1;
      // Observe reset and combinational gating away from the clock edge.
      check;
      @(posedge clk);
      if (!rst_n) begin capture = 0; control = 0; end
      else begin capture = {capture[1:0], ena}; control = {control[0], ui_in[1]}; end
      #1;
      check;
    end
    $display("PASS physical timing functional replay: five stages, reset and output gating; checks=%0d", checks);
    $finish;
  end
  initial begin #20000; $fatal(1, "functional timeout"); end
endmodule
