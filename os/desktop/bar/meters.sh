#!/bin/sh
# CPU / MEM / DISK readout for the dock.
#
# The design draws three stacked 3px bars. GTK cannot stack text inside one
# waybar module, so this renders the same three values on one line as short
# percentages, keeping the label order from the design.
set -u

# CPU over a 1s window -- /proc/stat deltas, no dependency on top or mpstat.
read_cpu() { awk '/^cpu /{print $2+$3+$4+$6+$7+$8, $5}' /proc/stat; }
set -- $(read_cpu); b_busy=$1; b_idle=$2
sleep 1
set -- $(read_cpu); a_busy=$1; a_idle=$2
d_busy=$((a_busy - b_busy)); d_idle=$((a_idle - b_idle))
total=$((d_busy + d_idle))
cpu=0; [ "$total" -gt 0 ] && cpu=$((100 * d_busy / total))

mem=$(awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{if(t>0) printf "%d", (t-a)*100/t; else print 0}' /proc/meminfo)
disk=$(df -P / 2>/dev/null | awk 'NR==2{gsub("%","",$5); print $5+0}')
[ -z "$disk" ] && disk=0

printf '{"text":"CPU %s  MEM %s  DISK %s","tooltip":"CPU %s%%\\nMemory %s%%\\nDisk %s%%"}\n' \
	"$cpu" "$mem" "$disk" "$cpu" "$mem" "$disk"
