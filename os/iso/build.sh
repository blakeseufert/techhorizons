#!/bin/sh -e
# Build the Tech Horizons ISO. Must run ON an Alpine x86_64 host
# (a VM or container) -- mkimage needs apk-tools and abuild natively.
#
#   ./iso/build.sh [outdir]
#
# Output: <outdir>/techhorizons-<ver>-x86_64.iso

# edge, not 3.23-stable: the built-in scrolling layout landed in Hyprland
# 0.54, and 3.23 is pinned at 0.51.1. The ISO bakes its own package set into
# an offline repo, so each image is a frozen snapshot -- students never track
# a rolling release. Set ALPINE_BRANCH=3.23-stable / ALPINE_TAG=v3.23 to go back.
ALPINE_BRANCH="${ALPINE_BRANCH:-master}"
ALPINE_TAG="${ALPINE_TAG:-edge}"
MIRROR="${MIRROR:-https://dl-cdn.alpinelinux.org/alpine}"
OUTDIR="${1:-$HOME/iso-out}"

SRC="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"

[ "$(id -u)" = 0 ] || { echo "run as root (it installs build deps)" >&2; exit 1; }

echo "==> build deps"
apk add --no-cache alpine-sdk build-base apk-tools alpine-conf busybox fakeroot \
	syslinux xorriso squashfs-tools mtools dosfstools grub-efi git \
	doas sudo mkinitfs

# abuild refuses to run as root, and mkimage calls abuild.
if ! id build >/dev/null 2>&1; then
	adduser -D build
	addgroup build abuild 2>/dev/null || true
fi
install -d -o build -g build /var/cache/distfiles
mkdir -p "$OUTDIR"

# mkimage runs as the unprivileged `build` user, which cannot traverse a
# 0700 /root. Always stage into a build-owned directory, then copy out.
STAGE=/home/build/iso-out
# Clear the stage: mkimage does not remove old images, so a stale ISO from a
# previous tag gets copied out alongside the new one and the two are hard to
# tell apart.
rm -rf "$STAGE"
install -d -o build -g build "$STAGE"

# A signing key is required even though we publish nothing -- mkimage signs the
# ISO's local apk index so the installer can verify it offline.
su build -c 'test -f "$HOME"/.abuild/*.rsa 2>/dev/null' \
	|| su build -c 'abuild-keygen -a -n -q'

echo "==> aports ($ALPINE_BRANCH)"
APORTS=/home/build/aports
if [ -d "$APORTS/.git" ]; then
	su build -c "git -C $APORTS fetch --depth=1 origin $ALPINE_BRANCH && git -C $APORTS reset --hard FETCH_HEAD"
else
	su build -c "git clone --depth=1 -b $ALPINE_BRANCH https://gitlab.alpinelinux.org/alpine/aports.git $APORTS"
fi

# genapkovl runs as the `build` user, which cannot read a 0700 /root. Stage the
# source somewhere build-readable and point TH_SRC there.
TH_SRC=/home/build/th-src
rm -rf "$TH_SRC"
mkdir -p "$TH_SRC"
cp -a "$SRC/." "$TH_SRC/"
chown -R build:build "$TH_SRC"
chmod -R a+rX "$TH_SRC"
export TH_SRC
TH_ALPINE_TAG="$ALPINE_TAG"
export TH_ALPINE_TAG

# Optional dev SSH key for the live ISO (debugging only).
if [ -n "${TH_DEV_KEY:-}" ] && [ -f "$TH_DEV_KEY" ]; then
	cp "$TH_DEV_KEY" /home/build/th-dev-key.pub
	chown build:build /home/build/th-dev-key.pub
	chmod 644 /home/build/th-dev-key.pub
	TH_DEV_KEY=/home/build/th-dev-key.pub
	export TH_DEV_KEY
	echo "    WARNING: dev sshd will be enabled in this ISO"
else
	TH_DEV_KEY=""
fi

echo "==> profile"
install -o build -g build -m644 "$SRC/iso/mkimg.techhorizons.sh"      "$APORTS/scripts/"
install -o build -g build -m755 "$SRC/iso/genapkovl-techhorizons.sh"  "$APORTS/scripts/"

# packages.list is the single source of truth; strip comments and blank lines.
TH_PACKAGES="$(sed -e 's/#.*//' -e '/^[[:space:]]*$/d' "$SRC/iso/packages.list" | tr '\n' ' ')"
export TH_PACKAGES
echo "    $(echo "$TH_PACKAGES" | wc -w) packages baked into the offline repo"

echo "==> mkimage"
su build -c "cd $APORTS/scripts && \
	TH_PACKAGES='$TH_PACKAGES' TH_SRC='$TH_SRC' TH_DEV_KEY='$TH_DEV_KEY' \
	TH_ALPINE_TAG='$TH_ALPINE_TAG' \
	./mkimage.sh \
		--tag '$ALPINE_TAG' \
		--arch x86_64 \
		--outdir '$STAGE' \
		--repository '$MIRROR/$ALPINE_TAG/main' \
		--repository '$MIRROR/$ALPINE_TAG/community' \
		--profile techhorizons"

echo "==> collecting"
found=0
for iso in "$STAGE"/*.iso; do
	[ -e "$iso" ] || continue
	cp -v "$iso" "$OUTDIR"/
	found=1
done
[ "$found" = 1 ] || { echo "mkimage produced no ISO" >&2; exit 1; }

echo
echo "==> done"
ls -lh "$OUTDIR"/*.iso
