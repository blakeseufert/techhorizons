# Tech Horizons OS — Alpine mkimage profile.
#
# Consumed by aports/scripts/mkimage.sh via --profile techhorizons.
# Everything listed in $apks lands in the ISO's apks/ repo, which is what makes
# a fully offline install possible. That is not incidental: students build their
# network during the course, so the installer cannot assume internet.

profile_techhorizons() {
	profile_standard

	profile_abbrev="techhorizons"
	# The file is TechHorizonsOS-<tag>-x86_64.iso, not alpine-techhorizons-...
	# -- it is what gets handed around on a stick, so it should say what it is.
	image_name="TechHorizonsOS"
	# BIOS boot: no "boot:" prompt, one second, straight in.
	syslinux_prompt=0
	syslinux_timeout=10

	title="Tech Horizons OS"
	desc="Tech Horizons OS — installer"
	arch="x86_64"
	kernel_flavors="lts"
	image_ext="iso"

	# quiet: students should see our splash, not kernel spam.
	kernel_cmdline="console=tty0 quiet"

	# Every driver class the initramfs needs to find its own boot media, plus
	# the disks we will later install onto. Omitting cdrom/ata/scsi/virtio here
	# is what caused "Mounting boot media failed" -- the kernel booted but the
	# initramfs could not mount the ISO it came from.
	#   cdrom/ata/scsi/usb -- boot from CD or USB stick
	#   virtio             -- boot under Proxmox/KVM for testing
	#   nvme/mmc/raid      -- the disks in real recycled laptops
	#   kms                -- DRM device, or cage/Hyprland has nothing to draw on
	#   squashfs           -- modloop
	initfs_features="ata base cdrom ext4 keymap kms mmc nvme raid scsi squashfs usb virtio"

	# Live installer environment + every package the installed system needs.
	# TH_PACKAGES is exported by iso/build.sh from iso/packages.list.
	apks="$apks $TH_PACKAGES"

	apkovl="genapkovl-techhorizons.sh"
}

# --- what the boot menu says ------------------------------------------------
# mkimage's own generators write "Linux lts" as the only menu entry and label
# the disc "alpine-techhorizons edge x86_64". Those are the first words a
# student sees. Both generators are overridden here (this file is sourced
# after mkimg.base.sh, so these definitions win); the shape of each entry is
# kept exactly as upstream writes it, including the microcode initrds, so
# only the words change.
syslinux_gen_config() {
	[ -z "$syslinux_serial" ] || echo "SERIAL $syslinux_serial"
	echo "TIMEOUT ${syslinux_timeout:-10}"
	echo "PROMPT ${syslinux_prompt:-1}"
	echo "DEFAULT ${kernel_flavors%% *}"
	local _f _p _initrd
	for _f in $kernel_flavors; do
		_initrd="/boot/initramfs-$_f"
		for _p in $initrd_ucode; do
			_initrd="$_p,$_initrd"
		done
		cat <<- EOF

		LABEL $_f
			MENU LABEL Tech Horizons OS
			KERNEL /boot/vmlinuz-$_f
			INITRD $_initrd
			FDTDIR /boot/dtbs-$_f
			APPEND $initfs_cmdline $kernel_cmdline
		EOF
	done
}

grub_gen_config() {
	local _f _p _initrd
	echo "set timeout=1"
	for _f in $kernel_flavors; do
		_initrd="/boot/initramfs-$_f"
		for _p in $initrd_ucode; do
			_initrd="$_p $_initrd"
		done
		cat <<- EOF

		menuentry "Tech Horizons OS" {
			linux	/boot/vmlinuz-$_f $initfs_cmdline $kernel_cmdline
			initrd	$_initrd
		}
		EOF
	done
}

# The volume label: what lsblk, a file manager, or the UEFI firmware calls the
# stick. grub's early config finds the disc by this label, and it calls the
# same function, so the two cannot drift apart.
gen_volid() {
	printf "%s" "TechHorizonsOS"
}
