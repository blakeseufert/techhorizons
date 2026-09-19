#!/bin/bash
# Build the Tech Horizons ISO on a dedicated Alpine builder VM, from your
# workstation. Nothing is ever installed on the Proxmox nodes themselves --
# they only host the VM.
#
#   ./iso/build-on-vm.sh
#
# Requires: SSH to the Proxmox node (used only as a jump host to reach the VM).
set -euo pipefail

NODE="${NODE:-px-main}"          # jump host only
BUILDER="${BUILDER:-10.0.5.170}" # th-builder VM (VM 200)
BUILDER_USER="${BUILDER_USER:-root}"
ISO_STORE="${ISO_STORE:-/mnt/pve/cephfs/template/iso}"

SRC="$(cd -- "$(dirname -- "$0")/.." && pwd)"
SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -J "root@$NODE")
TARGET="$BUILDER_USER@$BUILDER"

echo "==> waiting for builder sshd"
ssh -o BatchMode=yes "root@$NODE" \
	"n=0; until nc -z $BUILDER 22 2>/dev/null; do n=\$((n+1)); [ \$n -gt 60 ] && exit 1; sleep 3; done"

echo "==> shipping source to $BUILDER"
# tar over ssh rather than rsync -- the Alpine cloud image has no rsync.
# out/ holds previously built ISOs. Without excluding it every build
# shipped gigabytes of last build's output to the builder first.
tar czf - -C "$SRC" --exclude .git --exclude __pycache__ --exclude ./out . \
	| "${SSH[@]}" "$TARGET" 'rm -rf /root/th-src && mkdir -p /root/th-src && tar xzf - -C /root/th-src'

# TH_DEV_KEY=<pubkey> makes a DEV image with key-only root sshd, for debugging
# a running field node. Student images are built without it.
if [ -n "${TH_DEV_KEY:-}" ] && [ -f "$TH_DEV_KEY" ]; then
	echo "==> DEV IMAGE: shipping $TH_DEV_KEY, sshd will be enabled"
	"${SSH[@]}" "$TARGET" 'cat > /root/th-dev-key.pub' < "$TH_DEV_KEY"
	REMOTE_KEY=/root/th-dev-key.pub
else
	REMOTE_KEY=""
fi

echo "==> building (this pulls ~53 packages incl. chromium; expect a while)"
"${SSH[@]}" "$TARGET" "TH_DEV_KEY='$REMOTE_KEY' /root/th-src/iso/build.sh /root/iso-out"

echo "==> fetching ISO"
mkdir -p "$SRC/out"
NAME="$("${SSH[@]}" "$TARGET" 'ls -1 /root/iso-out/*.iso | head -1')"
[ -n "$NAME" ] || { echo "no ISO produced" >&2; exit 1; }
"${SSH[@]}" "$TARGET" "cat '$NAME'" > "$SRC/out/$(basename "$NAME")"

echo "==> publishing to $NODE:$ISO_STORE"
"${SSH[@]::${#SSH[@]}-2}" "root@$NODE" "mkdir -p '$ISO_STORE'"
"${SSH[@]}" "$TARGET" "cat '$NAME'" \
	| ssh -o BatchMode=yes "root@$NODE" "cat > '$ISO_STORE/$(basename "$NAME")'"

ls -lh "$SRC/out/$(basename "$NAME")"
echo "==> done -- attach it to the test VM and boot"
