`timescale 1ns/1ps
module memory_replay;
  reg clk = 0;
  always #5 clk = ~clk;
  reg ena = 0, rst_n = 0;
  reg [7:0] ui_in = 0, uio_in = 0;
  wire [7:0] uo_out, uio_out, uio_oe;
  tt_um_program_memory dut (.*);
  integer a, n, checks = 0;
  reg [15:0] expected;
  reg negative;

  function [15:0] word(input integer address);
    word = (address * 257) ^ 16'ha53c;
  endfunction

  task edge_command(input [1:0] command, input [7:0] payload);
    @(negedge clk);
    ui_in = {6'b0, command};
    uio_in = payload;
    @(posedge clk); #1;
    if (uio_out !== 0 || uio_oe !== 0) $fatal(1, "payload bus must remain input-only");
  endtask

  task check_word(input [15:0] value);
    ui_in[2] = 0; #1;
    if (uo_out !== value[7:0]) $fatal(1, "low byte addr=%0d expected=%h got=%h", a, value, uo_out);
    ui_in[2] = 1; #1;
    if (uo_out !== value[15:8]) $fatal(1, "high byte addr=%0d expected=%h got=%h", a, value, uo_out);
    checks = checks + 1;
  endtask

  initial begin
    negative = $test$plusargs("negative");
    edge_command(1, 0); // adapter reset only; no assumption about RAM state
    @(negedge clk); ena = 1; rst_n = 1;
    for (a = 0; a < 256; a = a + 1) begin
      expected = word(a);
      edge_command(1, a);
      edge_command(2, expected[7:0]);
      edge_command(3, expected[15:8]); // write output unspecified, do not inspect
    end
    for (n = 0; n < 256; n = n + 1) begin
      a = (n * 73 + 19) & 255;
      expected = word(a);
      edge_command(1, a);
      // Address staging must not read or change the registered response.
      if (n > 0) check_word(word(((n-1) * 73 + 19) & 255));
      edge_command(0, 0);
      if (negative && n == 0) check_word(expected ^ 1);
      check_word(expected);
      // Stage low byte with RAM disabled, then attempt commit while disabled.
      edge_command(2, ~expected[7:0]);
      check_word(expected);
      @(negedge clk); ena = 0;
      edge_command(3, ~expected[15:8]);
      if (uo_out !== 0) $fatal(1, "disabled output mask");
      @(negedge clk); ena = 1; ui_in = 2; #1;
      check_word(expected); // unmask before any clock edge: response held
      edge_command(0, 0);
      check_word(expected); // disabled write preserved the word
    end
    // Reset staging while RAM is disabled, then read retained address zero.
    @(negedge clk); rst_n = 0; ena = 0;
    edge_command(3, 0);
    if (uo_out !== 0) $fatal(1, "reset output mask");
    @(negedge clk); rst_n = 1; ena = 1; ui_in = 2;
    edge_command(0, 0);
    a = 0; check_word(word(0));
    $display("PASS memory RTL: load/read 256x16, staged/disabled hold, reset retains RAM; checks=%0d", checks);
    $finish;
  end
  initial begin #100000; $fatal(1, "timeout"); end
endmodule
