#!/bin/bash
# Build the Tech Horizons ISO on a remote Alpine host, from your workstation.
#
#   BUILDER=10.0.0.5 ./iso/build-on-vm.sh
#
# The builder must be Alpine x86_64, reachable over SSH, and the login must be
# able to run the build as root. mkimage needs apk-tools and abuild natively,
# so this cannot run on macOS or on a non-Alpine Linux.
#
#   BUILDER       required   builder host: address, hostname or ssh alias
#   BUILDER_USER  root       login on the builder
#   JUMP          unset      optional ssh jump host (ssh -J), for a builder on
#                            a network you cannot reach directly
#   ISO_STORE     unset      optional scp destination for the finished ISO,
#                            e.g. user@nas:/srv/iso
#
# Put your own values in th.env at the repo root (gitignored) instead of
# exporting them every time.
set -euo pipefail

SRC="$(cd -- "$(dirname -- "$0")/.." && pwd)"
[ -f "$SRC/th.env" ] && . "$SRC/th.env"

BUILDER="${BUILDER:?set BUILDER to the Alpine builder host -- see the header of this script}"
BUILDER_USER="${BUILDER_USER:-root}"
JUMP="${JUMP:-}"
ISO_STORE="${ISO_STORE:-}"

SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
[ -n "$JUMP" ] && SSH+=(-J "$JUMP")
TARGET="$BUILDER_USER@$BUILDER"

echo "==> waiting for builder sshd"
n=0
until "${SSH[@]}" -o ConnectTimeout=5 "$TARGET" true 2>/dev/null; do
	n=$((n + 1))
	[ "$n" -gt 60 ] && { echo "cannot reach $TARGET after 3 minutes" >&2; exit 1; }
	sleep 3
done

echo "==> shipping source to $BUILDER"
# tar over ssh rather than rsync -- the Alpine cloud image has no rsync.
tar czf - -C "$SRC" --exclude .git --exclude __pycache__ --exclude out . \
	| "${SSH[@]}" "$TARGET" 'rm -rf /root/th-src && mkdir -p /root/th-src && tar xzf - -C /root/th-src'

echo "==> building (this pulls ~53 packages incl. chromium; expect a while)"
"${SSH[@]}" "$TARGET" '/root/th-src/iso/build.sh /root/iso-out'

echo "==> fetching ISO"
mkdir -p "$SRC/out"
NAME="$("${SSH[@]}" "$TARGET" 'ls -1 /root/iso-out/*.iso | head -1')"
[ -n "$NAME" ] || { echo "no ISO produced" >&2; exit 1; }
BASE="$(basename "$NAME")"
"${SSH[@]}" "$TARGET" "cat '$NAME'" > "$SRC/out/$BASE"

if [ -n "$ISO_STORE" ]; then
	echo "==> publishing to $ISO_STORE"
	scp -o BatchMode=yes ${JUMP:+-J "$JUMP"} "$SRC/out/$BASE" "$ISO_STORE/"
fi

ls -lh "$SRC/out/$BASE"
echo "==> done -- attach it to a test VM and boot"
