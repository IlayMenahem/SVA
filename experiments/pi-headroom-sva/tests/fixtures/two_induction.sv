module main(input logic clk, input rst);
  logic a, b;
  always_ff @(posedge clk) begin
    if (rst) begin
      a <= 0;
      b <= 0;
    end else begin
      a <= 0;
      b <= a;
    end
  end
  property prop;
    @(posedge clk) disable iff (rst) b == 0;
  endproperty
endmodule
