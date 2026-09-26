#!/bin/sh
# Prove one ex15 obligation with JasperGold on the vlsi host.
# Usage: formal/run_jasper.sh <baseline|target|x_le_n|m_lt_x> [width] [engines] [timeout_s]
set -eu
obl=$1
width=${2:-32}
engines=${3:-Hp Ht N B}
limit=${4:-3600}
remote_dir=ex15-accel/$obl-w$width-$(date +%s)-$$

ssh vlsi "mkdir -p $remote_dir/rtl $remote_dir/formal"
scp -q rtl/ex15_ebmc.sv "vlsi:$remote_dir/rtl/"
scp -q formal/ex15_obligations.sv formal/ex15_bind.sv formal/prove.tcl "vlsi:$remote_dir/formal/"
ssh vlsi "cd $remote_dir && env EX15_OBL='$obl' EX15_WIDTH='$width' EX15_ENGINES='$engines' EX15_TIMEOUT='$limit' \
    /usr/bin/time -p jg -no_gui -tcl formal/prove.tcl"
