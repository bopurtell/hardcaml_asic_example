`timescale 1ns/1ps
module memory_core_replay;
  reg clock = 0;
  always #5 clock = ~clock;
  reg enable = 0, write_enable = 0;
  reg [7:0] address = 0;
  reg [15:0] write_data = 0;
  wire [15:0] read_data;
  program_memory_core dut (.*);
  integer a, n, checks = 0;
  reg known = 0;
  reg [15:0] previous;
  reg negative;

  function [15:0] word(input integer a);
    word = (a * 257) ^ 16'ha53c;
  endfunction

  task step(input bit en, input bit wr, input [7:0] addr,
            input [15:0] data, input bit observe, input [15:0] expected);
    @(negedge clock);
    enable = en; write_enable = wr; address = addr; write_data = data;
    #1;
    if (known && read_data !== previous) $fatal(1, "response changed before edge");
    @(posedge clock); #1;
    if (observe) begin
      if (read_data !== expected) $fatal(1, "core addr=%d expected=%h got=%h", addr, expected, read_data);
      checks = checks + 1;
    end
    known = observe;
    previous = expected;
  endtask

  initial begin
    negative = $test$plusargs("negative");
    for (a = 0; a < 256; a = a + 1) step(1, 1, a, word(a), 0, 0);
    // Changing addresses on every edge exposes asynchronous or extra-latency RTL.
    for (n = 0; n < 256; n = n + 1) begin
      a = (n * 73 + 19) & 255;
      step(1, 0, a, 0, 1, word(a) ^ ((negative && n == 0) ? 1 : 0));
    end
    for (a = 0; a < 256; a = a + 1) begin
      step(1, 0, a, 0, 1, word(a));
      step(0, 0, a ^ 255, 0, 1, word(a));
      step(0, 1, a, ~word(a), 1, word(a));
    end
    for (a = 255; a >= 0; a = a - 1) step(1, 0, a, 0, 1, word(a));
    for (a = 0; a < 256; a = a + 1) step(1, 1, a, (a & 1) ? 16'hffff : 0, 0, 0);
    for (a = 0; a < 256; a = a + 1) step(1, 0, a, 0, 1, (a & 1) ? 16'hffff : 0);
    $display("PASS Exact vendor core RTL: 2048 edges, checks=%0d; consecutive reads, latency-one, holds, disabled writes, overwrites", checks);
    $finish;
  end
  initial begin #100000; $fatal(1, "timeout"); end
endmodule
