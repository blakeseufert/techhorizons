#!/bin/sh
# Keep the reserved gap matching the drawer's actual width while it is open.
#
# The student resizes the drawer by dragging its right edge (resize_on_border).
# Nothing tells us when that happens -- Hyprland's event socket emits nothing
# at all for a resize, which was checked rather than assumed -- so this polls
# instead. It only runs while the drawer is visible and exits the moment it is
# stashed or closed, so nothing is left spinning in the background.
#
# It also enforces the limits: a drawer dragged past half the screen stops
# being a sidebar, and one dragged down to nothing is a drawer the student
# cannot grab again.
set -u

MIN_FRAC=0.18
MAX_FRAC=0.50
BAR_H=48
GAP_TOP=12
GAP_RIGHT=12
GAP_BOTTOM=22
GAP_LEFT=12
CLASS_RE='^(th-course|chrome-__opt_techhorizons_desktop_course\.html-Default)$'

state() {
	hyprctl clients -j | CLASS_RE="$CLASS_RE" python3 -c '
import json, os, re, sys
pat = re.compile(os.environ["CLASS_RE"])
for c in json.load(sys.stdin):
    if pat.match(c.get("class", "")):
        print(c["address"], c["workspace"]["name"], c["size"][0], c["at"][0])
        break'
}

mon_w=$(hyprctl monitors -j | python3 -c '
import json,sys
m = json.load(sys.stdin)[0]
print(int(m["width"] / (m.get("scale") or 1)))')
mon_h=$(hyprctl monitors -j | python3 -c '
import json,sys
m = json.load(sys.stdin)[0]
print(int(m["height"] / (m.get("scale") or 1)))')
min_w=$(awk -v w="$mon_w" -v f="$MIN_FRAC" 'BEGIN{printf "%d", w*f}')
max_w=$(awk -v w="$mon_w" -v f="$MAX_FRAC" 'BEGIN{printf "%d", w*f}')
height=$((mon_h - BAR_H))

last=""
while :; do
	set -- $(state)
	addr="${1:-}"; ws="${2:-}"; width="${3:-}"; x="${4:-}"

	# Gone, or stashed out of sight: our job is over.
	[ -z "$addr" ] && exit 0
	case "$ws" in special:*) exit 0 ;; esac

	# Clamp, and put the window back on the left edge if a drag moved it.
	want="$width"
	[ "$want" -lt "$min_w" ] && want="$min_w"
	[ "$want" -gt "$max_w" ] && want="$max_w"
	if [ "$want" != "$width" ] || [ "$x" != "0" ]; then
		hyprctl dispatch resizewindowpixel "exact $want $height,address:$addr" >/dev/null 2>&1
		hyprctl dispatch movewindowpixel "exact 0 0,address:$addr" >/dev/null 2>&1
	fi

	if [ "$want" != "$last" ]; then
		hyprctl keyword general:gaps_out \
			"$GAP_TOP,$GAP_RIGHT,$GAP_BOTTOM,$((GAP_LEFT + want))" >/dev/null 2>&1
		last="$want"
	fi

	sleep 0.4
done
