# Critical-path estimate (ABC stime) for the flattened Nangate45 netlist (v3).
# ABC sees flop outputs / macro outputs / ports as arrival 0 and flop inputs as endpoints:
# add the launching element's clk->q and the capture setup by hand (see README).
yosys -import
set srcs [lsort [glob src/ipu_*.sv]]
yosys read_verilog -sv -Isrc {*}$srcs
yosys read_liberty -lib macro/openram45_256x512_1r1w_TT_1p0V_25C.lib
yosys hierarchy -check -top ipu_top
yosys synth -top ipu_top -flatten
yosys dfflibmap -liberty $::env(LIB)
yosys abc -liberty $::env(LIB) -D $::env(PERIOD_PS) -script syn/abc_timing.abc -showtmp
