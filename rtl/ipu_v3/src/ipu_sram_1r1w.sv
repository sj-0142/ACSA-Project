// ipu_sram_1r1w -- score bank, v3: OpenRAM FreePDK45 1R1W macro openram45_256x512_1r1w
// (macro/openram45_256x512_1r1w.{v,lib}; 256 words x 512 b, port 0 write, port 1 read).
//
// Macro behaviour (from its model and liberty):
//   - all inputs are registered at the rising edge; active-low chip selects
//   - the write happens at the following falling edge
//   - read data appears 0.581 ns after the falling edge of the cycle after the read
//     request and is only valid until just after the next rising edge
//   - no write mask: every write is a full 512-bit row
// So, as seen by the IPU: read data is usable (and must be captured) in the cycle after
// re; a write is visible to a read issued in any later cycle.
// Read and write of the same address in the same cycle never happen in the IPU.
// `define IPU_SRAM_BEHAV for a behavioural array with the same cycle behaviour (lint).
module ipu_sram_1r1w #(
  parameter int W     = 512,
  parameter int DEPTH = 256
) (
  input  logic                     clk,
  input  logic                     re,
  input  logic [$clog2(DEPTH)-1:0] raddr,
  output logic [W-1:0]             rdata,
  input  logic                     we,
  input  logic [$clog2(DEPTH)-1:0] waddr,
  input  logic [W-1:0]             wdata
);
`ifdef IPU_SRAM_BEHAV
  logic [W-1:0] mem [0:DEPTH-1];

  always_ff @(posedge clk) begin
    if (we) mem[waddr] <= wdata;
    if (re) rdata <= mem[raddr];
  end
`else
`ifdef SYNTHESIS
  openram45_256x512_1r1w u_macro (
`else
  openram45_256x512_1r1w #(.VERBOSE(0)) u_macro (
`endif
    .clk0(clk), .csb0(~we), .addr0(waddr), .din0(wdata),
    .clk1(clk), .csb1(~re), .addr1(raddr), .dout1(rdata));
`endif
`ifndef SYNTHESIS
  // the macro's read and write of one address in one cycle is undefined
  always @(posedge clk)
    if (re && we && raddr == waddr)
      $display("ERROR ipu_sram_1r1w: read and write of row %0d in the same cycle", raddr);
`endif
endmodule
