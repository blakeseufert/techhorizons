#!/bin/sh
# Lock the screen. Bound to the bar's Lock button and SUPER+L.
#
# This is a SOFT lock, chosen deliberately. It is a fullscreen terminal that
# demands the password before giving the desktop back, and it matches the login
# screen -- same wordmark, same animation. It stops a classmate wandering past.
# It does NOT stop the person at the keyboard, who can switch VT or kill it.
#
# waylock is a genuine unescapable session lock but can only paint a flat
# colour; hyprlock, which could do both, is not packaged for Alpine. On
# classroom laptops where the student already knows the login password, looking
# like the rest of the OS was judged worth more than a lock its owner cannot
# escape. To swap back: exec waylock -init-color 0x05070F (waylock is installed).
# Run it under cage, the way the sign-in screen does.
#
# foot on its own could not be made to cover the screen reliably: mapped at its
# own size and fullscreened a frame later it came up a row short, with the
# wallpaper showing under the keybind rail. cage owns its output and hands its
# single client one size. The terminal still gets cleared from under us after
# the first frame -- AuthApp._full_repaint is what recovers from that.
# The drawer is floating AND pinned, which puts it above everything -- including
# a fullscreen lock screen. Locking with it open left the coursework sitting on
# top of the password box, which is not a lock. Stash it for the duration and
# put it back exactly as it was, so the student still returns to their page.
drawer_shown() {
	hyprctl clients -j 2>/dev/null | python3 -c '
import json, re, sys
pat = re.compile(r"^(th-course|chrome-__opt_techhorizons_desktop_course\.html-Default)$")
for c in json.load(sys.stdin):
    if pat.match(c.get("class", "")) and not c["workspace"]["name"].startswith("special:"):
        print("yes")
        break' 2>/dev/null
}

# Every popup panel is floating and pinned, which puts it above the lock the
# same way the drawer was. Close them outright -- unlike the drawer they hold
# no state worth coming back to.
for panel in clock network display system update; do
	hyprctl dispatch closewindow "class:^(th-panel-$panel)$" >/dev/null 2>&1 || true
done

restore=""
if [ "$(drawer_shown)" = "yes" ]; then
	restore=yes
	/opt/techhorizons/desktop/drawer.sh >/dev/null 2>&1 || true
fi

# cage keymap: no Ctrl+Alt+Fn -- same reason as hyprland.conf's kb_options.
XKB_DEFAULT_OPTIONS=srvrkeys:none cage -d -- foot \
	--app-id=th-lock \
	--config=/opt/techhorizons/greeter/foot.ini \
	--title="Tech Horizons Lock" \
	python3 /opt/techhorizons/tui/lock.py

[ "$restore" = "yes" ] && /opt/techhorizons/desktop/drawer.sh >/dev/null 2>&1 || true
exit 0
