#!/bin/bash
# Drive the test VM from the workstation, through the Proxmox host's QEMU
# monitor -- no SSH into the guest needed, so it works on a STUDENT image.
#
#   dev/vm.sh shot [name]        screenshot -> out/vm-<name>.png
#   dev/vm.sh key k1 k2 ...      QEMU sendkey names: ret tab esc ctrl-c ctrl-alt-f2
#   dev/vm.sh type "text"        type a string (letters, digits, punctuation)
#   dev/vm.sh click x y          left-click at console pixel x,y (DEV node only:
#                                the pointer is placed with hyprctl, the click
#                                comes from QEMU -- relative mouse moves are
#                                scaled by libinput and land anywhere)
#
# Screenshots are the only ground truth on a student image: read them, do not
# assume. A wizard that "must" be on step 3 has been on a root prompt before.
set -euo pipefail

SRC="$(cd -- "$(dirname -- "$0")/.." && pwd)"
[ -f "$SRC/th.env" ] && . "$SRC/th.env"

# TH_VMID  required  the test VM's id on the hypervisor
# TH_HOST  required  host running `qm` -- this drives the VM through the
#                    Proxmox QEMU monitor, so it is Proxmox-specific
# TH_NODE  required  the guest's own address, for `click` only
VMID="${TH_VMID:?set TH_VMID to the test VM id (or put it in th.env)}"
HOST="${TH_HOST:-${TH_JUMP:?set TH_HOST to the host running qm (or put it in th.env)}}"
NODE="${TH_NODE:-}"

monitor() { ssh -o BatchMode=yes "root@$HOST" 'while read -r l; do echo "$l" | qm monitor '"$VMID"' >/dev/null; sleep 0.12; done' 2>/dev/null; }

case "${1:-}" in
	shot)
		name="${2:-shot}"; mkdir -p "$SRC/out"
		ssh -o BatchMode=yes "root@$HOST" "echo 'screendump /tmp/th-vm.ppm' | qm monitor $VMID >/dev/null; cat /tmp/th-vm.ppm" 2>/dev/null \
		| python3 -c '
import sys, zlib, struct
d = sys.stdin.buffer.read(); parts = []; i = 0
while len(parts) < 4:
    while d[i:i+1].isspace(): i += 1
    j = i
    while not d[j:j+1].isspace(): j += 1
    parts.append(d[i:j]); i = j
i += 1; w, h = int(parts[1]), int(parts[2]); rgb = d[i:i+w*h*3]
raw = b"".join(b"\0" + rgb[y*w*3:(y+1)*w*3] for y in range(h))
def ch(t, b): return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t+b) & 0xffffffff)
sys.stdout.buffer.write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw, 6)) + ch(b"IEND", b""))
' > "$SRC/out/vm-$name.png"
		echo "$SRC/out/vm-$name.png" ;;
	key)
		shift; for k in "$@"; do echo "sendkey $k"; done | monitor ;;
	type)
		s="$2"; keys=()
		for ((i=0; i<${#s}; i++)); do c="${s:i:1}"
			case "$c" in
				[a-z0-9]) keys+=("$c");; [A-Z]) keys+=("shift-$(tr A-Z a-z <<<"$c")");;
				' ') keys+=(spc);; -) keys+=(minus);; .) keys+=(dot);; _) keys+=(shift-minus);;
				'!') keys+=(shift-1);; '@') keys+=(shift-2);; '#') keys+=(shift-3);; '$') keys+=(shift-4);;
				'%') keys+=(shift-5);; '^') keys+=(shift-6);; '&') keys+=(shift-7);; '*') keys+=(shift-8);;
				'(') keys+=(shift-9);; ')') keys+=(shift-0);; '=') keys+=(equal);; '+') keys+=(shift-equal);;
				'[') keys+=(bracket_left);; ']') keys+=(bracket_right);; '{') keys+=(shift-bracket_left);; '}') keys+=(shift-bracket_right);;
				';') keys+=(semicolon);; ':') keys+=(shift-semicolon);; "'") keys+=(apostrophe);; '"') keys+=(shift-apostrophe);;
				',') keys+=(comma);; '<') keys+=(shift-comma);; '>') keys+=(shift-dot);; '/') keys+=(slash);; '?') keys+=(shift-slash);;
				'\\') keys+=(backslash);; '|') keys+=(shift-backslash);; '`') keys+=(grave_accent);; '~') keys+=(shift-grave_accent);;
				*) echo "vm.sh: cannot type '$c'" >&2; exit 1;;
			esac
		done
		# One monitor session for the lot. A very long burst can leave a
		# modifier stuck; keep strings under ~80 characters and avoid quotes.
		for k in "${keys[@]}"; do echo "sendkey $k"; done | monitor ;;
	click)
		ssh -o BatchMode=yes -J "root@$HOST" "root@$NODE" 'sig=$(basename /run/user/1000/hypr/*); u=$(cat /etc/hostname)
		 su "$u" -c "XDG_RUNTIME_DIR=/run/user/1000 HYPRLAND_INSTANCE_SIGNATURE=$sig hyprctl dispatch movecursor '"$2 $3"'"' >/dev/null 2>&1
		sleep 0.4
		printf 'mouse_button 1\nmouse_button 0\n' | monitor ;;
	*) sed -n '2,15p' "$0"; exit 2 ;;
esac
