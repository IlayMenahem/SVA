# Jasper proof of one ex15 obligation.
# Environment: EX15_OBL (baseline|target|x_le_n|m_lt_x), EX15_WIDTH, EX15_ENGINES, EX15_TIMEOUT.
set obl     $::env(EX15_OBL)
set width   $::env(EX15_WIDTH)
set engines $::env(EX15_ENGINES)
set limit   $::env(EX15_TIMEOUT)

array set defines {
    baseline {ASSERT_TARGET}
    target   {ASSERT_TARGET ASSUME_X_LE_N ASSUME_M_LT_X}
    x_le_n   {ASSERT_X_LE_N}
    m_lt_x   {ASSERT_M_LT_X}
}
array set targets {
    baseline ex15.u_obl.target
    target   ex15.u_obl.target
    x_le_n   ex15.u_obl.h_x_le_n
    m_lt_x   ex15.u_obl.h_m_lt_x
}

clear -all
set define_args [concat {*}[lmap d $defines($obl) {list +define+$d}]]
analyze -sv12 {*}$define_args rtl/ex15_ebmc.sv formal/ex15_obligations.sv formal/ex15_bind.sv
elaborate -top ex15 -parameter WIDTH $width
clock clk
reset rst
get_design_info

set_prove_time_limit ${limit}s
set_engine_mode $engines
prove -property $targets($obl)
report -property $targets($obl) -detailed
puts "EX15_RESULT obl=$obl width=$width engines={$engines} status=[get_property_info $targets($obl) -list status] time=[get_property_info $targets($obl) -list time] engine=[get_property_info $targets($obl) -list engine]"
foreach p [get_property_list] { puts "EX15_PROPERTY $p [get_property_info $p -list type]" }
if {$obl eq "target"} {
    set_engine_mode {Ht B N}
    prove -property ex15.u_obl.c_done
    puts "EX15_COVER status=[get_property_info ex15.u_obl.c_done -list status] trace_length=[get_property_info ex15.u_obl.c_done -list trace_length]"
}
exit
