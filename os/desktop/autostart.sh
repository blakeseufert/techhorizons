#!/bin/sh
# Everything the student's session starts with. Nothing else ever launches on
# its own -- no notification daemon, no tray, no update nagging.
exec >>"${HOME:-/tmp}/.techhorizons-autostart.log" 2>&1
set -x

# Audio first, and this is not optional: waybar's pulseaudio module takes the
# ENTIRE bar down if no sound server is running -- waybar dies before it ever
# creates its layer surface, so the student gets no top bar and no obvious
# reason why. Start pipewire and wait for the socket before waybar.
pipewire &
pipewire-pulse &
sleep 1
wireplumber &

i=0
while [ $i -lt 60 ] && [ ! -S "$XDG_RUNTIME_DIR/pulse/native" ]; do
	i=$((i+1))
	sleep 0.25
done

waybar -c /opt/techhorizons/desktop/waybar/config \
       -s /opt/techhorizons/desktop/waybar/style.css &

# A normal browser window, NOT --app: the student keeps the tab strip, the
# address-free chrome and a real close button, so nothing depends on knowing a
# hotkey. The bar's VMs/Docker/Apps buttons open tabs in THIS window because
# they reuse the same --user-data-dir.
# Chromium decides it is a first run by the absence of this file, and then
# shows the welcome/what's-new tab over the dashboard. --no-first-run alone
# does not always cover it, and the sentinel does.
mkdir -p "$HOME/.th-chromium"
: > "$HOME/.th-chromium/First Run"

exec chromium \
	--test-type \
	--no-first-run \
	--no-service-autorun \
	--disable-features=TranslateUI,ChromeWhatsNewUI,PrivacySandboxSettings4 \
	--remote-debugging-port=9222 \
	--no-default-browser-check \
	--disable-sync \
	--disable-session-crashed-bubble \
	--hide-crash-restore-bubble \
	--user-data-dir="$HOME/.th-chromium" \
	--ozone-platform=wayland \
	--start-maximized \
	"file:///opt/techhorizons/desktop/home.html"
