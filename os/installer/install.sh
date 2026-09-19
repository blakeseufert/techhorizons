#!/bin/sh
# Tech Horizons OS — disk install.
#
# Invoked by tui/install.py with the student's answers in the environment:
#   TH_DISK        target block device, e.g. /dev/sda   (never the install media)
#   TH_HOSTNAME    server name
#   TH_PASSWORD    login password
#   TH_TIMEZONE    e.g. Australia/Melbourne
#
# Writes "PROGRESS <pct> <message>" lines on stdout; the server parses them and
# the UI shows them. Any non-zero exit is surfaced to the student verbatim.
#
# Packages come from the ISO's own apks/ repo, so this works with no internet.
set -eu
# apk's output is piped through a progress loop below, and without this a
# failed apk exits the PIPELINE with the loop's status: zero. The install then
# carried on to a "ready" screen over a root with nothing in it.
set -o pipefail

step() { echo "PROGRESS $1 $2"; }

: "${TH_DISK:?}" "${TH_HOSTNAME:?}" "${TH_PASSWORD:?}" "${TH_TIMEZONE:?}"

TARGET=/mnt

# --- locate the ISO's offline package repo ---------------------------------
# Alpine's initramfs mounts whatever it booted from under /media/<device>:
# /media/cdrom for an optical drive or a VM's virtual CD, but /media/sdb1,
# /media/sda1... for a USB stick -- which is what every real laptop boots
# from. A fixed list of three paths found the CD every time in the VM and
# nothing at all on a stick. Look for the repo itself instead, wherever the
# media landed, and prefer whatever apk was already pointed at.
REPO=""
for c in $(sed 's/#.*//' /etc/apk/repositories 2>/dev/null) /media/*/apks; do
	[ -f "$c/x86_64/APKINDEX.tar.gz" ] && { REPO="$c"; break; }
done
if [ -z "$REPO" ]; then
	echo "Could not find the package repository on the install media (mounted: $(ls /media 2>/dev/null | tr '\n' ' '))." >&2
	exit 1
fi

# --- refuse to eat the install media ---------------------------------------
# server.py checks this too; this is the last line of defence before dd-level damage.
BASE=$(basename "$TH_DISK")
while read -r dev _rest; do
	case "$dev" in /dev/*) ;; *) continue ;; esac
	d=$(basename "$dev")
	case "$d" in
		"$BASE"|"$BASE"p[0-9]*|"$BASE"[0-9]*)
			echo "$TH_DISK is currently in use as the install media. Refusing." >&2
			exit 1 ;;
	esac
done < /proc/mounts

if [ -d /sys/firmware/efi ]; then FIRMWARE=uefi; else FIRMWARE=bios; fi

step 5 "Preparing ${TH_DISK}…"
swapoff -a 2>/dev/null || true
wipefs -a "$TH_DISK" >/dev/null 2>&1 || true

# --- partition -------------------------------------------------------------
# GPT either way: BIOS boots via a 1MiB BIOS-boot partition, UEFI via the ESP.
step 10 "Creating partitions…"
if [ "$FIRMWARE" = uefi ]; then
	sfdisk --quiet --label gpt "$TH_DISK" <<-EOF
	,512M,U,*
	,,L
	EOF
else
	sfdisk --quiet --label gpt "$TH_DISK" <<-EOF
	,1M,21686148-6449-6E6F-744E-656564454649
	,512M,U
	,,L
	EOF
fi
partprobe "$TH_DISK" 2>/dev/null || true
sleep 2

# nvme0n1 -> nvme0n1p1 ; sda -> sda1
case "$TH_DISK" in
	*[0-9]) P="${TH_DISK}p" ;;
	*)      P="${TH_DISK}"  ;;
esac
if [ "$FIRMWARE" = uefi ]; then ESP="${P}1"; ROOT="${P}2"; else ESP="${P}2"; ROOT="${P}3"; fi

step 18 "Formatting…"
mkfs.vfat -F32 -n TH-BOOT "$ESP" >/dev/null
mkfs.ext4 -q -F -L techhorizons "$ROOT"

step 24 "Mounting…"
mkdir -p "$TARGET"
mount "$ROOT" "$TARGET"
mkdir -p "$TARGET/boot/efi"
mount "$ESP" "$TARGET/boot/efi"

# --- base system -----------------------------------------------------------
step 30 "Installing the base system…"
mkdir -p "$TARGET/etc/apk"
echo "$REPO" > "$TARGET/etc/apk/repositories"
apk add --root "$TARGET" --initdb --repository "$REPO" --no-cache --allow-untrusted \
	$(sed -e 's/#.*//' -e '/^[[:space:]]*$/d' /opt/techhorizons/packages.list | tr '\n' ' ') \
	2>&1 | while read -r line; do echo "PROGRESS 45 $line"; done

step 60 "Pointing apk at the network…"
# The target inherited the ISO's offline repo path, which does not exist once
# the machine reboots -- that leaves apk broken on every installed machine, so
# no app store, no updates and no future installs. Point it at the real
# mirrors for the branch this image was built from. The install itself still
# used the offline repo, so this changes nothing about installing offline.
TH_TAG=$(cat /opt/techhorizons/alpine-tag 2>/dev/null || echo edge)
cat > "$TARGET/etc/apk/repositories" <<-EOF
	https://dl-cdn.alpinelinux.org/alpine/$TH_TAG/main
	https://dl-cdn.alpinelinux.org/alpine/$TH_TAG/community
EOF

step 62 "Configuring…"
echo "$TH_HOSTNAME" > "$TARGET/etc/hostname"
cat > "$TARGET/etc/hosts" <<-EOF
	127.0.0.1  localhost $TH_HOSTNAME
	::1        localhost $TH_HOSTNAME
EOF

# fstab by UUID -- device names move around between boots on real hardware.
ROOT_UUID=$(blkid -s UUID -o value "$ROOT")
ESP_UUID=$(blkid -s UUID -o value "$ESP")
cat > "$TARGET/etc/fstab" <<-EOF
	UUID=$ROOT_UUID  /          ext4  rw,relatime 0 1
	UUID=$ESP_UUID   /boot/efi  vfat  rw,relatime 0 2
EOF

# evdev is an input handler with no modalias, so nothing autoloads it. Without
# it there are no /dev/input/event* nodes and the desktop gets no keyboard or
# mouse. Cheap insurance against a machine that boots to an unusable screen.
mkdir -p "$TARGET/etc"
for m in evdev psmouse hid_multitouch i2c_hid_acpi; do
	grep -qx "$m" "$TARGET/etc/modules" 2>/dev/null || echo "$m" >> "$TARGET/etc/modules"
done

ln -sf "/usr/share/zoneinfo/$TH_TIMEZONE" "$TARGET/etc/localtime"
echo "$TH_TIMEZONE" > "$TARGET/etc/timezone"

step 70 "Creating your account…"
# The student logs in as their server name -- one identity, not two.
chroot "$TARGET" /usr/sbin/adduser -D -g "Tech Horizons" "$TH_HOSTNAME" 2>/dev/null || true
printf '%s:%s\n' "$TH_HOSTNAME" "$TH_PASSWORD" | chroot "$TARGET" /usr/sbin/chpasswd
printf 'root:%s\n' "$TH_PASSWORD" | chroot "$TARGET" /usr/sbin/chpasswd
# plugdev is what our polkit rule keys on: it is the student's own network.
for grp in video input audio seat docker libvirt plugdev; do
	chroot "$TARGET" /usr/sbin/addgroup "$TH_HOSTNAME" "$grp" 2>/dev/null || true
done
install -D -m 644 /opt/techhorizons/desktop/polkit/10-techhorizons-network.rules \
	"$TARGET/etc/polkit-1/rules.d/10-techhorizons-network.rules"

step 76 "Setting up the login screen…"
# greetd runs the greeter as its own unprivileged user, which needs seat and
# device access to drive the compositor -- but no shell and no home.
# greetd chdir's into the greeter's home before running the session, so it
# needs one even though nobody ever logs in as this user.
chroot "$TARGET" /usr/sbin/adduser -D -h /var/lib/greeter -s /sbin/nologin greeter 2>/dev/null || true
mkdir -p "$TARGET/var/lib/greeter"
chroot "$TARGET" /bin/chown -R greeter:greeter /var/lib/greeter
for grp in video input seat; do
	chroot "$TARGET" /usr/sbin/addgroup greeter "$grp" 2>/dev/null || true
done
mkdir -p "$TARGET/etc/greetd"
# The greeter is a terminal program on vt1, not a browser: it keeps the login
# screen retro and means the whole web stack only comes up AFTER unlock.
cat > "$TARGET/etc/greetd/config.toml" <<-EOF
	[terminal]
	vt = 1

	[default_session]
	command = "/opt/techhorizons/greeter/session.sh"
	user = "greeter"
EOF
# Readable by the greeter user; greetd refuses to start if it cannot read this.
chmod 0644 "$TARGET/etc/greetd/config.toml"

step 78 "Enabling services…"
# udev, not mdev -- wlroots/libinput enumerate input through udev. Both were
# enabled before, which worked by luck; mdev is now gone so the installed
# system matches the ISO exactly.
for svc in devfs dmesg udev udev-trigger udev-settle hwdrivers; do
	chroot "$TARGET" /sbin/rc-update add "$svc" sysinit 2>/dev/null || true
done
chroot "$TARGET" /sbin/rc-update del mdev sysinit 2>/dev/null || true
for svc in modules sysctl hostname bootmisc syslog; do
	chroot "$TARGET" /sbin/rc-update add "$svc" boot 2>/dev/null || true
done
# seatd must start before greetd: cage cannot open a DRM session without it,
# which is exactly how the ISO failed before seatd was added there.
# sshd is on deliberately: the machine is a server, and Stage 2 of the course
# has students SSH into it. Root login stays off -- they use their own account.
mkdir -p "$TARGET/etc/ssh"
if [ -f "$TARGET/etc/ssh/sshd_config" ]; then
	sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' "$TARGET/etc/ssh/sshd_config"
	grep -q '^PermitRootLogin' "$TARGET/etc/ssh/sshd_config" \
		|| echo 'PermitRootLogin no' >> "$TARGET/etc/ssh/sshd_config"
fi

for svc in seatd dbus elogind networkmanager chronyd greetd sshd docker libvirtd; do
	chroot "$TARGET" /sbin/rc-update add "$svc" default 2>/dev/null || true
done
for svc in mount-ro killprocs savecache; do
	chroot "$TARGET" /sbin/rc-update add "$svc" shutdown 2>/dev/null || true
done

step 85 "Installing Tech Horizons…"
mkdir -p "$TARGET/opt/techhorizons"
cp -a /opt/techhorizons/. "$TARGET/opt/techhorizons/"

# The managed browser policy (no sign-in promo, no sync, no password manager,
# no web store) is written into the live ISO's /etc by the overlay -- and was
# never copied here, so every installed machine ran a stock consumer chromium
# while the policy sat on the USB stick.
if [ -d /etc/chromium/policies ]; then
	mkdir -p "$TARGET/etc/chromium"
	cp -a /etc/chromium/policies "$TARGET/etc/chromium/"
fi

# Build the pointer theme -- both formats, see assets/cursor/build.sh.
chroot "$TARGET" /bin/sh /opt/techhorizons/desktop/assets/cursor/build.sh \
	/usr/share/icons/TechHorizons || \
	echo "install: pointer theme did not build -- the stock arrow will be used" >&2

# The lock screen's Restart and Shut down run as the student, who cannot reboot
# -- /sbin/reboot says "Operation not permitted" and loginctl silently does
# nothing. One doas rule, for one script, which takes one of two arguments.
# Both the student and the greeter: the sign-in screen offers the same two
# buttons as the lock screen, and it runs as its own unprivileged user.
mkdir -p "$TARGET/etc/doas.d"
{
	printf 'permit nopass %s as root cmd /opt/techhorizons/desktop/power.sh\n' "$TH_HOSTNAME"
	printf 'permit nopass greeter as root cmd /opt/techhorizons/desktop/power.sh\n'
} > "$TARGET/etc/doas.d/techhorizons.conf"
chmod 0400 "$TARGET/etc/doas.d/techhorizons.conf"

# foot only reads our config when it is passed with -c, so a terminal the
# student opens any other way came up in foot's own grey with a tiny font.
# /etc/xdg is the system-wide default every foot picks up.
mkdir -p "$TARGET/etc/xdg/foot"
cp /opt/techhorizons/greeter/foot.ini "$TARGET/etc/xdg/foot/foot.ini"

# A file:// page cannot read /etc/hostname, so bake the server's name into the
# placeholder surfaces at install time. th-hub will serve this properly later.
for f in "$TARGET"/opt/techhorizons/desktop/*.html; do
	[ -e "$f" ] && sed -i "s/@@SERVER_NAME@@/$TH_HOSTNAME/g" "$f"
done

# Dev builds only: the ISO only carries /root/.ssh/authorized_keys when it was
# built with TH_DEV_KEY, so this whole block is absent from a student image.
# It exists so a broken desktop session can be diagnosed in place rather than
# by reinstalling.
if [ -f /root/.ssh/authorized_keys ]; then
	install -d -m 700 "$TARGET/home/$TH_HOSTNAME/.ssh"
	cp /root/.ssh/authorized_keys "$TARGET/home/$TH_HOSTNAME/.ssh/authorized_keys"
	chmod 600 "$TARGET/home/$TH_HOSTNAME/.ssh/authorized_keys"
	chroot "$TARGET" /bin/chown -R "$TH_HOSTNAME:$TH_HOSTNAME" "/home/$TH_HOSTNAME/.ssh"

	# Key-only root, never password: /opt is root-owned, so editing the shell
	# config on a running machine otherwise means a full reinstall.
	install -d -m 700 "$TARGET/root/.ssh"
	cp /root/.ssh/authorized_keys "$TARGET/root/.ssh/authorized_keys"
	chmod 600 "$TARGET/root/.ssh/authorized_keys"
	sed -i 's/^#*PermitRootLogin.*/PermitRootLogin prohibit-password/' \
		"$TARGET/etc/ssh/sshd_config"
	echo "# dev image: key-only root login enabled by TH_DEV_KEY" \
		>> "$TARGET/etc/ssh/sshd_config"
fi

step 88 "Building the boot image…"
# The installed system needs its own initramfs built with drivers for the
# disk it will boot from. Without this the kernel loads but cannot mount
# root: "mounting /dev/sdaN on /sysroot failed". Same class of failure as
# the ISO's own initfs_features -- the target needs it too.
#   ata/scsi/usb/virtio -- the controller root lives behind
#   nvme/mmc            -- real recycled laptops
#   ext4                -- our root filesystem
mkdir -p "$TARGET/etc/mkinitfs"
cat > "$TARGET/etc/mkinitfs/mkinitfs.conf" <<-EOF
	features="ata base cdrom ext4 keymap kms mmc nvme raid scsi usb virtio"
EOF

step 88 "Installing fonts…"
# Archivo is the display face in the design and Alpine has no package for it,
# so it ships with us under the OFL. Inter comes from font-inter like normal.
if [ -d /opt/techhorizons/desktop/assets/fonts ]; then
	install -d -m 755 "$TARGET/usr/share/fonts/archivo"
	for f in /opt/techhorizons/desktop/assets/fonts/*.ttf; do
		[ -e "$f" ] || continue
		install -m 644 "$f" "$TARGET/usr/share/fonts/archivo/"
	done
	install -m 644 /opt/techhorizons/desktop/assets/fonts/OFL-Archivo.txt \
		"$TARGET/usr/share/fonts/archivo/" 2>/dev/null || true
	# Without a cache rebuild nothing resolves "Archivo" and every heading
	# silently falls back to Inter.
	chroot "$TARGET" /usr/bin/fc-cache -f >/dev/null 2>&1 || true
fi

step 90 "Making it bootable…"
mkdir -p "$TARGET/proc" "$TARGET/sys" "$TARGET/dev"
mount -t proc none "$TARGET/proc"
mount --rbind /sys "$TARGET/sys"
mount --rbind /dev "$TARGET/dev"

# Alpine's initramfs only loads the modules named in the `modules=` kernel
# parameter -- it does not probe. Without this the initramfs contains ext4.ko
# but never inserts it, and root mounting fails with "No such file or
# directory" even though the device and filesystem are both fine.
#   sd-mod/virtio_scsi/ahci -- the disk controller
#   nvme/mmc_block          -- real recycled laptops
#   usb-storage             -- installs onto USB media
#   ext4                    -- our root filesystem
mkdir -p "$TARGET/etc/default"
cat > "$TARGET/etc/default/grub" <<-EOF
	GRUB_DISTRIBUTOR="Tech Horizons"
	GRUB_DEFAULT=0
	GRUB_TIMEOUT=0
	GRUB_TIMEOUT_STYLE=hidden
	GRUB_DISABLE_RECOVERY=true
	GRUB_DISABLE_SUBMENU=y
	GRUB_CMDLINE_LINUX_DEFAULT="modules=sd-mod,usb-storage,virtio_scsi,ahci,nvme,mmc_block,ext4 rootfstype=ext4 quiet"
EOF

KVER=$(ls "$TARGET/lib/modules" 2>/dev/null | head -1)
[ -n "$KVER" ] || { echo "No kernel modules found in the installed system." >&2; exit 1; }
chroot "$TARGET" /sbin/mkinitfs "$KVER"

if [ "$FIRMWARE" = uefi ]; then
	chroot "$TARGET" /usr/sbin/grub-install --target=x86_64-efi \
		--efi-directory=/boot/efi --bootloader-id=techhorizons --removable
else
	chroot "$TARGET" /usr/sbin/grub-install --target=i386-pc "$TH_DISK"
fi
chroot "$TARGET" /usr/sbin/grub-mkconfig -o /boot/grub/grub.cfg

step 97 "Finishing up…"
for m in proc sys dev boot/efi ""; do
	[ -n "$m" ] && umount -lR "$TARGET/$m" 2>/dev/null || true
done
umount -lR "$TARGET" 2>/dev/null || true
sync

step 100 "Done"
