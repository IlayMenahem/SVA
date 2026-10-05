// Example design for jgu: a mod-10 counter with an enable and an unconstrained input k.
module counter (
    input  logic       clk,
    input  logic       rst,
    input  logic       en,
    input  logic [3:0] k,
    output logic [3:0] q
);
    always_ff @(posedge clk) begin
        if (rst) begin
            q <= 4'd0;
        end else if (en) begin
            q <= (q == 4'd9) ? 4'd0 : q + 4'd1;
        end
    end
endmodule
