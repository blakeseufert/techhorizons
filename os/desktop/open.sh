#!/bin/sh
# Open one of the OS's surfaces in the student's browser -- or jump to it if it
# is already open.
#
# Passing a URL to a chromium already running with the same --user-data-dir
# hands it to that instance, but as a NEW tab every time: press VMs four times
# and you get four identical tabs. Chromium has no "focus the tab showing this
# URL" switch, so ask its DevTools endpoint, which autostart.sh binds to
# localhost. If that is not answering we just open a tab as before -- a
# duplicate tab is a far better failure than a button that does nothing.
set -eu

case "${1:-}" in
	vms)     PAGE=vms.html ;;
	docker)  PAGE=docker.html ;;
	apps)    PAGE=apps.html ;;
	network) PAGE=network.html ;;
	course)  PAGE=course.html ;;
	*)       PAGE=home.html ;;
esac
URL="file:///opt/techhorizons/desktop/$PAGE"
PORT=9222

focus_existing() {
	python3 - "$URL" "$PORT" <<'PY' 2>/dev/null
import json, sys, urllib.request

url, port = sys.argv[1], sys.argv[2]
base = "http://127.0.0.1:%s" % port
try:
    with urllib.request.urlopen(base + "/json/list", timeout=1) as r:
        tabs = json.load(r)
except Exception:
    sys.exit(1)

for tab in tabs:
    if tab.get("type") != "page":
        continue
    # ignore the fragment: the course drawer moves through #anchors and is
    # still the same tab
    if tab.get("url", "").split("#")[0] != url:
        continue
    try:
        urllib.request.urlopen(base + "/json/activate/" + tab["id"], timeout=1).read()
    except Exception:
        sys.exit(1)
    sys.exit(0)
sys.exit(1)
PY
}

if focus_existing; then
	# The tab is frontmost, but the window may not be: bring it up too.
	hyprctl dispatch focuswindow class:chromium >/dev/null 2>&1 || true
	exit 0
fi

exec chromium \
	--user-data-dir="$HOME/.th-chromium" \
	--ozone-platform=wayland \
	"$URL"
