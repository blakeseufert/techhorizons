#!/bin/sh
# Toggle one of the bar's popup panels.
#
# A panel is a small floating terminal pinned above the dock, positioned by a
# windowrule in hyprland.conf. Clicking the same bar button again closes it,
# which is what "toggle" has to mean for a button that is always on screen.
#
#   panel.sh clock | network | display | system
#
# These are terminals rather than browser windows on purpose: they report on
# the machine itself, they have to run commands to do it (ip, nmcli, upower),
# and a file:// page can do neither.
set -eu

name="${1:-}"
case "$name" in
	clock)   cmd="/opt/techhorizons/desktop/panel/clock.sh" ;;
	network) cmd="python3 /opt/techhorizons/desktop/panel/network.py" ;;
	display) cmd="python3 /opt/techhorizons/desktop/panel/display.py" ;;
	system)  cmd="btop --force-utf" ;;
	*) echo "panel.sh: unknown panel '$name'" >&2; exit 2 ;;
esac

app_id="th-panel-$name"

# Already open? Then this click is the one that closes it.
if hyprctl clients -j 2>/dev/null | grep -q "\"class\": *\"$app_id\""; then
	hyprctl dispatch closewindow "class:^($app_id)$" >/dev/null 2>&1 || true
	exit 0
fi

# Only one panel at a time -- two overlapping popups above the dock is clutter.
for other in clock network display system; do
	[ "$other" = "$name" ] && continue
	hyprctl dispatch closewindow "class:^(th-panel-$other)$" >/dev/null 2>&1 || true
done

foot \
	--app-id="$app_id" \
	--config=/opt/techhorizons/greeter/foot.ini \
	--title="$name" \
	--override=font=JetBrains\ Mono:size=11 \
	$cmd &

# A popover closes when you click somewhere else. Without this the panel was
# a window with no close button, and the one way out -- clicking the same
# dock button again -- is not something anyone guesses first time. Watch
# Hyprland's event socket: once our window has had focus, the first focus
# change to anything else closes it. Clicking the dock itself is not a focus
# change (it is a layer, not a window), so the toggle still works.
exec python3 - "$app_id" <<'PY'
import json, os, socket, subprocess, sys

app_id = sys.argv[1]
run = os.environ.get("XDG_RUNTIME_DIR") or "/run/user/%d" % os.getuid()
sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") or os.listdir(f"{run}/hypr")[0]

def present() -> bool:
    out = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True).stdout
    try:
        return any(c.get("class") == app_id for c in json.loads(out or "[]"))
    except ValueError:
        return False

s = socket.socket(socket.AF_UNIX)
s.connect(f"{run}/hypr/{sig}/.socket2.sock")
focused = False
buf = b""
while True:
    data = s.recv(4096)
    if not data:
        break
    buf += data
    while b"\n" in buf:
        line, buf = buf.split(b"\n", 1)
        line = line.decode(errors="replace")
        if line.startswith("activewindow>>"):
            cls = line.split(">>", 1)[1].split(",", 1)[0]
            if cls == app_id:
                focused = True
            elif focused:
                subprocess.run(["hyprctl", "dispatch", "closewindow", f"class:^({app_id})$"],
                               capture_output=True)
                sys.exit(0)
        elif line.startswith("closewindow>>") and not present():
            sys.exit(0)
PY
