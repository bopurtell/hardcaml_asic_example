`timescale 1ns/1ps
module bank_replay;
  reg clk = 0, ena = 0, rst_n = 0;
  reg [7:0] ui_in = 0, uio_in = 0;
  wire [7:0] uo_out, uio_oe, uio_out;
  tt_um_sram_budget dut (.*);
  always #5 clk = ~clk;

  task command(input [1:0] bank, input [1:0] op, input [7:0] payload);
    @(negedge clk);
    ui_in = {3'b0, bank, 1'b0, op};
    uio_in = payload;
    @(posedge clk); #1;
    if (uio_oe !== 0 || uio_out !== 0) $fatal(1, "payload bus must be input-only");
  endtask

  function [15:0] pattern(input integer bank, input integer address);
    pattern = (16'h5a93 * (bank + 1)) ^ (address * 257);
  endfunction
  integer a, b;
  reg [15:0] word;
  initial begin
    command(0, 1, 0);
    ena = 1; rst_n = 1;
    // Write different words at the same address in each bank before reading
    // anything back; a missing bank-enable or aliased bank now corrupts data.
    for (a = 0; a < 256; a = a + 1) begin
      command(0, 1, a);
      for (b = 0; b < 3; b = b + 1) begin
        word = pattern(b, a);
        command(b, 2, word[7:0]);
        command(b, 3, word[15:8]);
      end
      command(3, 3, 8'hff); // unused bank code cannot write any memory
    end
    for (a = 255; a >= 0; a = a - 1) begin
      command(0, 1, a);
      for (b = 2; b >= 0; b = b - 1) begin
        word = pattern(b, a);
        command(b, 0, 0);
        if (uo_out !== word[7:0]) $fatal(1, "low byte: bank %d address %d", b, a);
        ui_in[2] = 1; #1;
        if (uo_out !== word[15:8]) $fatal(1, "high byte: bank %d address %d", b, a);
      end
      command(3, 0, 0);
      if (uo_out !== 0) $fatal(1, "unused bank code must return zero");
    end
    $display("PASS: read back 768 independent bank/address pairs");
    $finish;
  end
endmodule
