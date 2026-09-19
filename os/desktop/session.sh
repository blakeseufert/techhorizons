#!/bin/sh
# The student's desktop session, started by greetd once they log in.
exec >>"${HOME:-/tmp}/.techhorizons-session.log" 2>&1
set -x

export XDG_RUNTIME_DIR="/run/user/$(id -u)"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 0700 "$XDG_RUNTIME_DIR"
export XDG_SESSION_TYPE=wayland
export XDG_CURRENT_DESKTOP=Hyprland
export MOZ_ENABLE_WAYLAND=1
export QT_QPA_PLATFORM=wayland

# The config lives in /opt and is not user-editable: this OS is on rails, and
# a student cannot break their desktop into a state we cannot support.
# dbus-run-session, not bare Hyprland: without a session bus waybar cannot
# start ("Cannot autolaunch D-Bus without X11 $DISPLAY") and silently never
# draws its bar.
exec dbus-run-session -- Hyprland -c /opt/techhorizons/desktop/hyprland.conf
