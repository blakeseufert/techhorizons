#!/bin/sh
# greetd's greeter session: the Tech Horizons login screen.
#
# The greeter is a terminal app, but it does NOT run bare on the VT. greetd
# hands a greeter the VT as stdin without a controlling terminal, so a curses
# or Textual app's tcsetattr silently fails: the password echoes in plaintext
# and keystrokes never arrive. Running it inside a real terminal fixes both.
#
# cage is a single-window compositor and foot is a plain terminal, so this is
# still a terminal UI -- no browser anywhere in the login path.
exec >>/tmp/techhorizons-greeter.log 2>&1
set -x

export XDG_RUNTIME_DIR="/run/user/$(id -u)"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 0700 "$XDG_RUNTIME_DIR"
export XDG_SESSION_TYPE=wayland
export WLR_LIBINPUT_NO_DEVICES=1
# cage keymap: no Ctrl+Alt+Fn -- same reason as hyprland.conf's kb_options.
export XKB_DEFAULT_OPTIONS=srvrkeys:none

i=0
while [ $i -lt 50 ] && [ ! -S /run/seatd.sock ]; do
	i=$((i+1)); sleep 0.2
done

exec cage -d -- foot \
	--config=/opt/techhorizons/greeter/foot.ini \
	--title=th-greeter \
	python3 /opt/techhorizons/tui/greet.py
