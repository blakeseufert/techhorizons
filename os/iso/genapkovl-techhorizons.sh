#!/bin/sh -e
# Builds the apkovl overlay baked into the live ISO.
#
# Its only job is to boot the machine straight into our terminal installer.
# No login prompt, no shell, no Alpine setup script -- the first thing a
# student ever sees is the Tech Horizons installer, full screen.

HOST=techhorizons-installer
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/etc/runlevels/sysinit" "$tmp/etc/runlevels/boot" \
         "$tmp/etc/runlevels/default" "$tmp/etc/local.d" "$tmp/etc/apk"

echo "$HOST" > "$tmp/etc/hostname"

# Input drivers the installer cannot work without, loaded explicitly.
#
# evdev is an input HANDLER with no modalias, so udev never autoloads it, and
# Alpine's lts kernel builds it as a module. Without it the kernel finds the
# keyboard but creates no /dev/input/event* nodes at all, libinput sees
# nothing, and the UI accepts neither keyboard nor mouse.
#
# psmouse drives PS/2 mice and most laptop touchpads. serio devices do not
# reliably emit a modalias, so it too needs loading by name -- without it the
# machine has a keyboard but no pointer.
#
# hid_multitouch and i2c_hid_acpi cover modern I2C touchpads. They normally
# autoload from ACPI, but they are cheap to name and a laptop with no pointer
# is unusable.
mkdir -p "$tmp/etc"
cat > "$tmp/etc/modules" <<-MODULES
	evdev
	psmouse
	hid_multitouch
	i2c_hid_acpi
MODULES

# No /etc/apk/repositories in the overlay: the initramfs writes the one it
# actually booted from (/media/cdrom/apks on a CD, /media/sdb1/apks on a
# stick). The hardcoded cdrom path this used to ship was wrong on every real
# laptop, and install.sh reads this file first when looking for the repo.

# No login prompts on the live ISO. Alpine's stock inittab puts a getty on
# tty1-6 and the live root has no password, so once the installer was gone --
# quit key, crash, Ctrl+Alt+F2 -- "root" and enter was a shell with the disk
# tools on it. The installer is the only thing this image runs; init keeps
# sysinit, the runlevels, ctrl-alt-del and shutdown, and nothing that asks for
# a name.
cat > "$tmp/etc/inittab" <<-INITTAB
	::sysinit:/sbin/openrc sysinit
	::sysinit:/sbin/openrc boot
	::wait:/sbin/openrc default
	::ctrlaltdel:/sbin/reboot
	::shutdown:/sbin/openrc shutdown
INITTAB

# /etc/apk/world is what the live root is actually built from. The profile's
# $apks only fills the ISO's offline repo -- without this the installer
# environment boots with nothing in it (no cage, no chromium, not even python3).
#
# Kept deliberately small: the live root is a tmpfs, so every package here
# costs RAM on a 4GB recycled laptop. The full target package set stays in the
# repo and is installed onto the disk, not into RAM.
cat > "$tmp/etc/apk/world" <<'WORLD'
alpine-base
busybox
cage
foot
py3-textual
py3-rich
python3
dbus
elogind
eudev
udev-init-scripts
libinput
seatd
seatd-openrc
mesa-dri-gallium
mesa-egl
mesa-gles
font-inter
font-jetbrains-mono
font-jetbrains-mono-nerd
networkmanager
dosfstools
e2fsprogs
parted
util-linux
efibootmgr
grub
grub-efi
grub-bios
WORLD

# Chromium is the UI toolkit for the INSTALLED system only -- the live ISO now
# runs a terminal installer, which is why chromium is absent from the world
# above. That matters: the live root is a tmpfs, and chromium is several
# hundred MB of RAM on a laptop that may only have four gigabytes.
#
# On the installed system chromium is locked down by managed policy
# rather than by flags -- flags can be lost, policy cannot. This kills the
# first-run sign-in promo, sync, metrics and every other consumer-browser
# affordance a student should never see on an appliance.
#
# The address bar is real, so file:// is fenced to our own pages: without the
# blocklist, typing "file:///" walks the whole disk in a directory listing,
# and chrome://flags is a settings panel we said this OS does not have. The
# path in a filter is a PREFIX and must not end in "*": with a star the
# allowlist matched nothing and the browser blocked the dashboard itself.
mkdir -p "$tmp/etc/chromium/policies/managed"
cat > "$tmp/etc/chromium/policies/managed/techhorizons.json" <<'POLICY'
{
  "BrowserSignin": 0,
  "SyncDisabled": true,
  "PromotionalTabsEnabled": false,
  "MetricsReportingEnabled": false,
  "DefaultBrowserSettingEnabled": false,
  "SearchSuggestEnabled": false,
  "PasswordManagerEnabled": false,
  "BookmarkBarEnabled": false,
  "ShowHomeButton": false,
  "AutofillAddressEnabled": false,
  "AutofillCreditCardEnabled": false,
  "SafeBrowsingEnabled": false,
  "BackgroundModeEnabled": false,
  "PrivacySandboxPromptEnabled": false,
  "RestoreOnStartup": 5,
  "HideWebStoreIcon": true,
  "URLBlocklist": ["file://*", "chrome://flags", "chrome://extensions", "chrome://settings"],
  "URLAllowlist": ["file:///opt/techhorizons/desktop/"]
}
POLICY

rc_add() { mkdir -p "$tmp/etc/runlevels/$2"; ln -sf "/etc/init.d/$1" "$tmp/etc/runlevels/$2/$1"; }

# udev, not mdev: wlroots/libinput enumerate input devices through udev, and
# with only busybox mdev cage dies with "no input devices".
rc_add devfs     sysinit
rc_add dmesg     sysinit
rc_add udev      sysinit
rc_add udev-trigger sysinit
rc_add udev-settle  sysinit
rc_add hwdrivers sysinit

rc_add modloop   boot
rc_add modules   boot
rc_add sysctl    boot
rc_add hostname  boot
rc_add bootmisc  boot
rc_add syslog    boot

# Only services whose packages are in /etc/apk/world above -- enabling a
# service that is not installed is why networkmanager silently never ran.
rc_add seatd     default
rc_add dbus      default
rc_add elogind   default
rc_add networkmanager default
rc_add local     default

rc_add mount-ro  shutdown
rc_add killprocs shutdown
rc_add savecache shutdown

# local.d runs at the end of the default runlevel -- launch the installer.
cat > "$tmp/etc/local.d/techhorizons-installer.start" <<'START'
#!/bin/sh
# Everything here is logged -- a silent failure on a student's laptop is
# indistinguishable from a broken machine.
exec >>/var/log/techhorizons-installer.log 2>&1
set -x

# cage is a Wayland compositor and refuses to start without a runtime dir.
# We are launched from an OpenRC init script, not a login session, so nothing
# has set one up for us.
export XDG_RUNTIME_DIR=/run/user/0
mkdir -p "$XDG_RUNTIME_DIR"
chmod 0700 "$XDG_RUNTIME_DIR"
export XDG_SESSION_TYPE=wayland
# A VM console can present zero input devices. Harmless on real hardware --
# this only skips wlroots' "no input devices" abort, it disables nothing.
export WLR_LIBINPUT_NO_DEVICES=1

# Belt and braces on top of /etc/modules: the `modules` service may run
# before modloop is mounted, in which case evdev is not there to load yet.
# local.d runs at the very end of the default runlevel, so it always is.
for m in evdev psmouse hid_multitouch i2c_hid_acpi; do
	modprobe "$m" 2>/dev/null || true
done

# Alpine's libseat has no 'builtin' backend, so cage cannot open a DRM
# session on its own. seatd provides one; let libseat autodetect it.
i=0
while [ $i -lt 50 ] && [ ! -S /run/seatd.sock ]; do
	i=$((i+1)); sleep 0.2
done

# The installer is a terminal app: cage gives us a compositor, foot gives it a
# real pty. No browser is involved, and none is installed in the live image.
#
# In a loop, not exec'd: if the wizard ever exits -- a crash, a quit key that
# slipped through -- the alternative is whatever init puts on tty1 next, and
# on a live Alpine root that is a passwordless login. Ctrl+Alt+Fn is disabled
# in the keymap for the same reason (srvrkeys:none); the other VTs have no
# getty on this image either, see /etc/inittab in the overlay.
export XKB_DEFAULT_OPTIONS=srvrkeys:none
while :; do
	cage -d -- foot \
		--config=/opt/techhorizons/greeter/foot.ini \
		--title=th-installer \
		python3 /opt/techhorizons/tui/install.py
	sleep 1
done
START
chmod +x "$tmp/etc/local.d/techhorizons-installer.start"

# Our own source tree rides along in the overlay so the live installer has it.
# TH_SRC is exported by iso/build.sh and points at the repo checkout.
if [ -n "${TH_SRC:-}" ] && [ -d "$TH_SRC" ]; then
	mkdir -p "$tmp/opt/techhorizons"
	for d in tui installer desktop course greeter; do
		[ -d "$TH_SRC/$d" ] && cp -a "$TH_SRC/$d" "$tmp/opt/techhorizons/"
	done
	# install.sh needs the package list at install time; iso/ itself is not
	# shipped, so place the list where the installer looks for it.
	cp "$TH_SRC/iso/packages.list" "$tmp/opt/techhorizons/packages.list"
	# The installer needs to know which Alpine branch this image was built
	# from, so it can point the installed system at the matching mirrors.
	printf '%s\n' "${TH_ALPINE_TAG:-edge}" > "$tmp/opt/techhorizons/alpine-tag"
	# Strip macOS AppleDouble turds if the source came off a Mac.
	find "$tmp/opt/techhorizons" -name '._*' -delete
else
	echo "genapkovl: TH_SRC unset or missing -- installer will not be on the ISO" >&2
	exit 1
fi

# Build-time opt-in ONLY: TH_DEV_KEY=<path to pubkey> enables sshd in the live
# ISO for debugging. Never set this for a build handed to students.
if [ -n "${TH_DEV_KEY:-}" ] && [ -f "$TH_DEV_KEY" ]; then
	echo "genapkovl: WARNING enabling dev sshd in this ISO" >&2
	echo openssh >> "$tmp/etc/apk/world"
	mkdir -p "$tmp/root/.ssh"
	cp "$TH_DEV_KEY" "$tmp/root/.ssh/authorized_keys"
	chmod 700 "$tmp/root/.ssh"; chmod 600 "$tmp/root/.ssh/authorized_keys"
	rc_add sshd default
fi

tar -c -C "$tmp" etc opt root 2>/dev/null | gzip -9n > techhorizons.apkovl.tar.gz \
	|| tar -c -C "$tmp" etc opt | gzip -9n > techhorizons.apkovl.tar.gz
