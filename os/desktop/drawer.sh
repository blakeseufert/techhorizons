#!/bin/sh
# The coursework drawer. Bound to the bar's TECH HORIZONS button and SUPER+C.
#
# Three things this has to get right, and the obvious implementation gets all
# three wrong:
#
#   It must not reload. A student can glance at it for five seconds or leave it
#   for five hours and it has to come back on the same page, at the same scroll
#   position, mid-sentence. So hiding it means parking the window on a special
#   workspace, never closing it. The version before this killed the process on
#   every toggle.
#
#   It must take space, not cover it. Opening a drawer over the top of the
#   student's work would hide the thing they are following the instructions
#   for. `addreserved` shrinks the area the tiling layout may use, so the
#   windows shuffle over and stay fully visible.
#
#   It must not move. The layout scrolls horizontally, so a tiled drawer would
#   slide off the moment a VM window opened. Floating and pinned keeps it where
#   it is regardless of what happens in the layout behind it.
set -eu

# Match on the class chromium actually reports. --class is ignored by this
# build -- the app-id comes from the --app URL -- so the long generated name is
# the real one, and the short one is only here in case a later chromium starts
# honouring the flag.
CLASS_RE='^(th-course|chrome-__opt_techhorizons_desktop_course\.html-Default)$'
STASH="special:drawer"
BAR_H=48
FRACTION=0.26

# Everything below addresses the window by its address rather than by a class
# pattern: hyprctl dispatch takes the pattern as one shell word, the regex has
# backslashes and parentheses in it, and getting that through su, ssh and
# hyprctl intact is not worth the debugging.
find_window() {
	hyprctl clients -j | CLASS_RE="$CLASS_RE" python3 -c '
import json, os, re, sys
pat = re.compile(os.environ["CLASS_RE"])
for c in json.load(sys.stdin):
    if pat.match(c.get("class", "")):
        print(c["address"], c["workspace"]["name"],
              "pinned" if c.get("pinned") else "unpinned")
        break'
}

# Hyprland refuses to move a PINNED window to another workspace -- and says
# "ok" while refusing. That one silent no-op is what made the drawer flaky:
# every hide left the window sitting on top of the layout while the gap it had
# reserved was given back, so tiled windows ended up underneath it. Unpin
# first, and only toggle when it is actually pinned, because `pin` is a toggle
# and blindly firing it turns pinning ON for an unpinned window.
set_pin() {
	want="$1"; addr="$2"; now="$3"
	[ "$want" = "$now" ] && return 0
	hyprctl dispatch pin "address:$addr" >/dev/null 2>&1 || true
}

geom() {
	hyprctl monitors -j | python3 -c '
import json,sys
m = json.load(sys.stdin)[0]
scale = m.get("scale") or 1
print(m["name"], int(m["width"]/scale), int(m["height"]/scale))'
}

# Reserving the space with a left GAP, not with the monitor's reserved area.
#
# `monitor,addreserved` is the obvious tool and it does work, but setting it
# makes Hyprland re-evaluate the whole monitor rule -- and the catch-all rule
# says "preferred", which is not necessarily the mode you are running. On the
# test node the screen dropped from 1280x800 to 1280x720 every time the drawer
# opened, and after a few of those the virtual output got stuck at 800x600
# until the session restarted. Not something to ship anywhere near a student's
# only laptop.
#
# gaps_out shrinks the tiling area just as effectively and never goes near a
# modeset. The stock gaps come from hyprland.conf; the drawer adds its width to
# the left one and puts it back on close.
GAP_TOP=12
GAP_RIGHT=12
GAP_BOTTOM=22
GAP_LEFT=12

reserve() {
	hyprctl keyword general:gaps_out "$GAP_TOP,$GAP_RIGHT,$GAP_BOTTOM,$((GAP_LEFT + $1))" >/dev/null
}

set -- $(geom)
MON="$1"; MON_W="$2"; MON_H="$3"
W=$(awk -v w="$MON_W" -v f="$FRACTION" 'BEGIN{printf "%d", w*f}')
H=$((MON_H - BAR_H))

show() {
	addr="$1"; pin_state="${2:-unpinned}"
	reserve "$W"
	ws=$(hyprctl activeworkspace -j | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
	hyprctl dispatch movetoworkspacesilent "$ws,address:$addr" >/dev/null 2>&1 || true
	hyprctl dispatch setfloating "address:$addr" >/dev/null 2>&1 || true
	hyprctl dispatch resizewindowpixel "exact $W $H,address:$addr" >/dev/null 2>&1 || true
	hyprctl dispatch movewindowpixel "exact 0 0,address:$addr" >/dev/null 2>&1 || true
	set_pin pinned "$addr" "$pin_state"

	# Keep the reserved gap matching the width while the student drags the
	# drawer's edge. It exits by itself when the drawer is stashed.
	pkill -f "[d]rawer-sync.sh" >/dev/null 2>&1 || true
	setsid /opt/techhorizons/desktop/drawer-sync.sh >/dev/null 2>&1 &

	# The layout scrolls, so the window the student is actually working in can
	# be sitting where the drawer just appeared -- opening a reference panel
	# that covers the thing you are referencing it for. Only intervene when
	# that has happened: `fit active` fills the free area with the active
	# column, which both scrolls it clear and sizes it to what is left.
	x=$(hyprctl activewindow -j | python3 -c '
import json, sys
try:
    w = json.load(sys.stdin)
except Exception:
    w = {}
at = w.get("at") or [0, 0]
print(at[0] if not w.get("floating") else 99999)' 2>/dev/null || echo 99999)
	case "$x" in
		''|*[!0-9-]*) ;;
		*) [ "$x" -lt "$W" ] && hyprctl dispatch layoutmsg fit active >/dev/null 2>&1 || true ;;
	esac
}

hide() {
	addr="$1"; pin_state="${2:-pinned}"
	pkill -f "[d]rawer-sync.sh" >/dev/null 2>&1 || true
	set_pin unpinned "$addr" "$pin_state"
	hyprctl dispatch movetoworkspacesilent "$STASH,address:$addr" >/dev/null 2>&1 || true
	reserve 0
}

set -- $(find_window)
addr="${1:-}"; ws="${2:-}"; pin_state="${3:-unpinned}"

if [ -z "$addr" ]; then
	# First open of the session: start it, wait for the window, then place it.
	# --app so it has no tab strip or address bar; this is a drawer, not a
	# browser. Its own profile dir keeps it out of the student's tab history.
	chromium \
		--app=file:///opt/techhorizons/desktop/course.html \
		--test-type \
		--class=th-course \
		--no-first-run \
		--no-default-browser-check \
		--disable-sync \
		--user-data-dir="$HOME/.th-chromium-course" \
		--ozone-platform=wayland >/dev/null 2>&1 &
	n=0
	while [ -z "$(find_window)" ] && [ $n -lt 80 ]; do sleep 0.25; n=$((n+1)); done
	set -- $(find_window)
	[ -n "${1:-}" ] || exit 0
	show "$1" "${3:-unpinned}"
	exit 0
fi

case "$ws" in
	"$STASH") show "$addr" "$pin_state" ;;
	*)        hide "$addr" "$pin_state" ;;
esac
