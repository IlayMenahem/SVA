module main(input clk, input rst);
  logic bit_state;
  always_ff @(posedge clk) begin
    if (rst) bit_state <= 1'b0;
    else bit_state <= 1'b1;
  end
  property prop;
    @(posedge clk) disable iff (rst) !bit_state;
  endproperty
endmodule
