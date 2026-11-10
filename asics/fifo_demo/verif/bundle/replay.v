`timescale 1ns/1ps
module replay;
  reg clk = 0, ena = 0, rst_n = 0;
  reg [7:0] ui_in = 0, uio_in = 0;
  wire [7:0] uo_out, uio_out, uio_oe;
  tt_um_controlled_fifo dut(.*);
  integer fd, scanned, index = 0;
  integer known, en, reset_n, data_in, requests, before_data, before_pins, after_data, after_pins;
  reg [4095:0] trace_path;

  task check;
    input [7:0] data, pins, oe;
    input [255:0] phase;
    begin
      if (uo_out !== data || uio_out !== pins || uio_oe !== oe)
        $fatal(1, "trace=%0d phase=%0s input ena=%0d rst_n=%0d ui=%02h uio=%02h expected=%02h/%02h/%02h actual=%02h/%02h/%02h",
               index, phase, ena, rst_n, ui_in, uio_in, data, pins, oe, uo_out, uio_out, uio_oe);
    end
  endtask

  // Combinational mask probes contain no clock edge. Unmasking must reveal
  // exactly the reference state, including a held valid response.
  task probes;
    input [7:0] data, pins;
    integer e, r;
    begin
      for (e = 0; e < 2; e = e + 1)
        for (r = 0; r < 2; r = r + 1) begin
          ena = e; rst_n = r; uio_in = requests ^ 8'hfc; #1;
          if (e && r) check(data, pins, 8'hfc, "no-edge unmask");
          else check(0, 0, 0, "no-edge mask");
        end
      ena = en; rst_n = reset_n; uio_in = requests; #1;
      if (en && reset_n) check(data, pins, 8'hfc, "restored inputs");
      else check(0, 0, 0, "restored mask");
    end
  endtask

  initial begin
    if (!$value$plusargs("trace=%s", trace_path)) $fatal(1, "missing trace");
    fd = $fopen(trace_path, "r");
    if (!fd) $fatal(1, "cannot open trace");
    scanned = $fscanf(fd, "%d %d %d %d %d %d %d %d %d\n",
                      known, en, reset_n, data_in, requests, before_data, before_pins, after_data, after_pins);
    while (scanned == 9) begin
      clk = 0; ena = en; rst_n = reset_n; ui_in = data_in; uio_in = requests; #1;
      if (known) probes(before_data, before_pins);
      clk = 1; #1;
      if (en && reset_n) check(after_data, after_pins, 8'hfc, "after edge");
      else check(0, 0, 0, "after edge mask");
      clk = 0; #1;
      probes(after_data, after_pins);
      index = index + 1;
      scanned = $fscanf(fd, "%d %d %d %d %d %d %d %d %d\n",
                        known, en, reset_n, data_in, requests, before_data, before_pins, after_data, after_pins);
    end
    if (scanned != -1 || index == 0) $fatal(1, "malformed/empty trace at %0d", index);
    $display("PASS RTL edges=%0d (directed + seed=20261012 cycles=4096)", index);
    $finish;
  end
endmodule
