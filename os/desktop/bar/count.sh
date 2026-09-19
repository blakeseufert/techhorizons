#!/bin/sh
# Dock counters: how many VMs / containers are actually running.
# Prints waybar JSON. Never fails -- a module that emits bad JSON renders as a
# blank pill, which looks like a broken dock.
set -u
kind="${1:-vms}"

# NOTE: `grep -c` prints 0 AND exits non-zero when nothing matches, so a
# `|| echo 0` fallback fires as well and the count comes out as "0\n0" --
# invalid JSON. `|| true` keeps the single 0 that grep already printed.
count_lines() { grep -c '[^[:space:]]' || true; }

case "$kind" in
	vms)
		n=$(virsh --connect qemu:///system list --state-running --name 2>/dev/null | count_lines)
		unit="VM"; label="running VMs"
		;;
	containers)
		n=$(docker ps --quiet 2>/dev/null | count_lines)
		unit="CT"; label="running containers"
		;;
	*) n=0; unit=""; label="" ;;
esac

# Belt and braces: anything non-numeric becomes 0 rather than breaking JSON.
case "$n" in
	''|*[!0-9]*) n=0 ;;
esac

# The unit rides along in the pill: a bare "0" next to another bare "0" tells a
# student nothing about which is which.
printf '{"text":"%s %s","tooltip":"%s %s"}\n' "$n" "$unit" "$n" "$label"
