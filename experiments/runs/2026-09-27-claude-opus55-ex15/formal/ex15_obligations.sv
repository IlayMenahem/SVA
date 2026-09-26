// Proof obligations for ex15 (Large Lemma Miners, hard/ex15_ebmc.sv).
// Each obligation is asserted when `ASSERT_<ID>` is defined and assumed when
// `ASSUME_<ID>` is defined, so every run proves exactly one obligation under
// exactly its DAG dependencies.
//
// DAG:  target -> {h_x_le_n, h_m_lt_x}; the helpers have no dependencies.

module ex15_obligations #(parameter WIDTH = 32) (
    input logic             clk,
    input logic             rst,
    input logic [1:0]       state,
    input logic [WIDTH-1:0] x,
    input logic [WIDTH-1:0] m,
    input logic [WIDTH-1:0] n
);
    localparam logic [1:0] DONE = 2'd2;

    // Original target: the body of `property prop` in ex15_ebmc.sv, verbatim.
    property p_target;
        @(posedge clk) disable iff (rst) (state != DONE || n <= 0 || m < n);
    endproperty

    // The loop counter never passes the bound latched at reset.
    property p_x_le_n;
        @(posedge clk) disable iff (rst) (x <= n);
    endproperty

    // m is either untouched or a strictly earlier value of x.
    property p_m_lt_x;
        @(posedge clk) disable iff (rst) (m == 0 || m < x);
    endproperty

`ifdef ASSERT_TARGET
    target: assert property (p_target);
    // Nonvacuity: the target's antecedent is reachable with m updated.
    c_done: cover property (@(posedge clk) disable iff (rst) state == DONE && n != 0 && m != 0);
`endif
`ifdef ASSERT_X_LE_N
    h_x_le_n: assert property (p_x_le_n);
`elsif ASSUME_X_LE_N
    h_x_le_n: assume property (p_x_le_n);
`endif
`ifdef ASSERT_M_LT_X
    h_m_lt_x: assert property (p_m_lt_x);
`elsif ASSUME_M_LT_X
    h_m_lt_x: assume property (p_m_lt_x);
`endif
endmodule
