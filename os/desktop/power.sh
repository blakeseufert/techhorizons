#!/bin/sh
# Restart or shut down the Field Node. Runs as root via doas.
#
# The lock screen's buttons did nothing at all before this, and the reason is
# dull: the student's session is not root, and none of the obvious routes work
# for an unprivileged user on this image. /sbin/reboot answers "Operation not
# permitted", openrc-shutdown is not even on their PATH, and `loginctl reboot`
# returns success and then does nothing -- elogind and polkit are both running,
# so that one is the most annoying of the three.
#
# doas with one rule, for this script only, is the narrow version of "let the
# student turn their own computer off".
set -eu

case "${1:-}" in
	reboot)   managed="openrc-shutdown -r now"; direct="/sbin/reboot";   forced="reboot -f" ;;
	poweroff) managed="openrc-shutdown -p now"; direct="/sbin/poweroff"; forced="poweroff -f" ;;
	*) echo "usage: power.sh reboot|poweroff" >&2; exit 2 ;;
esac

sync

# Same ladder as the installer's restart button, and for the same reason: the
# managed path can exit 0 on this image without taking the machine down.
$managed >/dev/null 2>&1 && sleep 6
$direct  >/dev/null 2>&1 && sleep 6
/bin/busybox $forced
