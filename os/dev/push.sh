#!/bin/bash
# Push the working tree onto a running field node and restart what changed.
#
#   dev/push.sh                 sync, reload Hyprland, restart the bar
#   dev/push.sh --greeter       ...then restart greetd (back to the sign-in screen)
#   dev/push.sh --wizard        ...then run the setup wizard in a window
#
# For the lock screen, push and then press SUPER+L on the node. Restarting cage
# from outside the session races its teardown and leaves a stray window.
#
# For iterating on the OS without rebuilding the ISO. Only files under
# /opt/techhorizons are pushed -- packages, kernel, initramfs and anything in
# the live ISO overlay still need a build.
#
# The node must be a DEV node: build the image with TH_DEV_KEY. There is no
# console route any more -- Ctrl+Alt+Fn is disabled in every keymap the OS
# uses (srvrkeys:none), so the gettys on tty2-6 cannot be reached from the
# keyboard. Student images ship sshd running but with no key and
# PermitRootLogin no, so nothing on one is reachable either. That is the point.
set -euo pipefail

NODE="${TH_NODE:-10.0.5.168}"      # the field node
JUMP="${TH_JUMP:-px-slow}"         # Proxmox host used only to reach its LAN
SRC="$(cd -- "$(dirname -- "$0")/.." && pwd)"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=15 -J "root@$JUMP" "root@$NODE")

echo "==> syncing to $NODE"
# tar over ssh, not rsync: Alpine has no rsync.
# COPYFILE_DISABLE stops macOS tar writing AppleDouble "._name" companions for
# every file. They are invisible on a Mac and inert for most things, but
# hyprcursor-util reads "._default" as a cursor shape and fails the whole theme
# with "couldn't parse meta" -- which points at the wrong file entirely. The
# ISO build already strips them; this path did not.
COPYFILE_DISABLE=1 \
tar czf - -C "$SRC" --exclude .git --exclude __pycache__ --exclude ./out \
	--exclude ./iso --exclude ./docs \
	tui desktop greeter installer course 2>/dev/null \
	| "${SSH[@]}" 'tar xzf - -C /opt/techhorizons'

# The desktop pages are file:// URLs and cannot read /etc/hostname, so the
# installer bakes the node name in. Re-apply it or every page says
# "@@SERVER_NAME@@" until the next install.
"${SSH[@]}" 'name=$(cat /etc/hostname)
for f in /opt/techhorizons/desktop/*.html; do
	[ -e "$f" ] && sed -i "s/@@SERVER_NAME@@/$name/g" "$f"
done
find /opt/techhorizons -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
find /opt/techhorizons -name '._*' -delete 2>/dev/null || true
# tar carries my workstation uid across; the installer leaves these root-owned
chown -R root:root /opt/techhorizons
# same as the installer does: the system-wide default config for foot
# (no apostrophes in here -- this block is inside a single-quoted string)
mkdir -p /etc/xdg/foot && cp /opt/techhorizons/greeter/foot.ini /etc/xdg/foot/foot.ini'

# Everything below runs inside the student session, which owns the Wayland
# socket -- root cannot talk to Hyprland without borrowing its environment.
HYPR='export XDG_RUNTIME_DIR=/run/user/1000
export HYPRLAND_INSTANCE_SIGNATURE=$(basename /run/user/1000/hypr/* 2>/dev/null)
user=$(cat /etc/hostname)
as_user() { su "$user" -c "XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR HYPRLAND_INSTANCE_SIGNATURE=$HYPRLAND_INSTANCE_SIGNATURE $1"; }'

echo "==> reloading the session"
"${SSH[@]}" "$HYPR"'
as_user "hyprctl reload" >/dev/null 2>&1 || echo "   (no session -- sitting at the sign-in screen?)"
# SIGHUP does not reload waybar, it drops its layer surface and leaves the
# process alive with no bar on screen. Restart it properly.
if pgrep -x waybar >/dev/null; then
	pkill -x waybar 2>/dev/null || true
	n=0; while pgrep -x waybar >/dev/null && [ $n -lt 20 ]; do sleep 0.25; n=$((n+1)); done
	as_user "hyprctl dispatch exec \"waybar -c /opt/techhorizons/desktop/waybar/config -s /opt/techhorizons/desktop/waybar/style.css\"" >/dev/null
fi'

case "${1:-}" in
	--greeter)
		echo "==> restarting greetd (this ends the desktop session)"
		"${SSH[@]}" 'rc-service greetd restart' ;;
	--wizard)
		echo "==> opening the setup wizard (do NOT drive it past Confirm -- it installs)"
		"${SSH[@]}" "$HYPR"'
		as_user "hyprctl dispatch exec \"foot --config=/opt/techhorizons/greeter/foot.ini python3 /opt/techhorizons/tui/install.py\"" >/dev/null' ;;
	"") ;;
	*) echo "unknown option: $1" >&2; exit 2 ;;
esac

echo "==> done"
