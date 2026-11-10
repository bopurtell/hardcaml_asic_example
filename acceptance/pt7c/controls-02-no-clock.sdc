###############################################################################
# Created by write_sdc
###############################################################################
current_design tt_um_pt7_timing
###############################################################################
# Timing Constraints
###############################################################################
set_false_path\
    -from [get_ports {ena}]\
    -to [get_pins {_4_/D}]
set_false_path\
    -from [get_ports {rst_n}]\
    -to [list [get_pins {_2_/RESET_B}]\
           [get_pins {_3_/RESET_B}]\
           [get_pins {_4_/RESET_B}]\
           [get_pins {_5_/RESET_B}]\
           [get_pins {_6_/RESET_B}]]
###############################################################################
# Environment
###############################################################################
set_load -pin_load 0.0060 [get_ports {uo_out[7]}]
set_load -pin_load 0.0060 [get_ports {uo_out[6]}]
set_load -pin_load 0.0060 [get_ports {uo_out[5]}]
set_load -pin_load 0.0060 [get_ports {uo_out[4]}]
set_load -pin_load 0.0060 [get_ports {uo_out[3]}]
set_load -pin_load 0.0060 [get_ports {uo_out[2]}]
set_load -pin_load 0.0060 [get_ports {uo_out[1]}]
set_load -pin_load 0.0060 [get_ports {uo_out[0]}]
set_load -pin_load 0.0060 [get_ports {uio_out[7]}]
set_load -pin_load 0.0060 [get_ports {uio_out[6]}]
set_load -pin_load 0.0060 [get_ports {uio_out[5]}]
set_load -pin_load 0.0060 [get_ports {uio_out[4]}]
set_load -pin_load 0.0060 [get_ports {uio_out[3]}]
set_load -pin_load 0.0060 [get_ports {uio_out[2]}]
set_load -pin_load 0.0060 [get_ports {uio_out[1]}]
set_load -pin_load 0.0060 [get_ports {uio_out[0]}]
set_load -pin_load 0.0060 [get_ports {uio_oe[7]}]
set_load -pin_load 0.0060 [get_ports {uio_oe[6]}]
set_load -pin_load 0.0060 [get_ports {uio_oe[5]}]
set_load -pin_load 0.0060 [get_ports {uio_oe[4]}]
set_load -pin_load 0.0060 [get_ports {uio_oe[3]}]
set_load -pin_load 0.0060 [get_ports {uio_oe[2]}]
set_load -pin_load 0.0060 [get_ports {uio_oe[1]}]
set_load -pin_load 0.0060 [get_ports {uio_oe[0]}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {ui_in[7]}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {ui_in[6]}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {ui_in[5]}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {ui_in[4]}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {ui_in[3]}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {ui_in[2]}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {ui_in[1]}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {ui_in[0]}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {ena}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {clk}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {rst_n}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {uio_in[7]}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {uio_in[6]}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {uio_in[5]}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {uio_in[4]}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {uio_in[3]}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {uio_in[2]}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {uio_in[1]}]
set_driving_cell -lib_cell sg13cmos5l_buf_4 -pin {X} -input_transition_rise 0.0000 -input_transition_fall 0.0000 [get_ports {uio_in[0]}]
set_timing_derate -early 0.9500
set_timing_derate -late 1.0500
###############################################################################
# Design Rules
###############################################################################
set_max_fanout 10.0000 [current_design]
