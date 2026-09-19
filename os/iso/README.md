# Building the Tech Horizons ISO

This directory builds `TechHorizonsOS-<tag>-x86_64.iso` — a ~1.3 GB Alpine
image that boots straight into a Chromium-kiosk installer and installs the
whole OS **with no network**.

If you are picking this up cold, read [Two ways to build](#two-ways-to-build)
and then just run `./iso/build-on-vm.sh`. Everything else here is detail for
when that goes wrong.

## The one constraint that shapes everything

**Students have no internet until the networking stage of the course.** So the
installer cannot download anything. Every package the installed system will
ever need is baked into an offline apk repo inside the ISO at build time. That
is why the image is 1.3 GB, why `packages.list` matters so much, and why the
build needs a signing key even though nothing is published.

## Two ways to build

### From your workstation (normal path)

```sh
./iso/build-on-vm.sh
```

Ships the source to the builder VM over SSH, builds there, pulls the ISO back
to `out/`, and publishes a copy to the cluster's ISO store. You need SSH to the
Proxmox node; it is used only as a jump host.

### On an Alpine host directly

```sh
./iso/build.sh [outdir]
```

Must run **on Alpine x86_64, as root**. `mkimage` needs `apk-tools` and
`abuild` natively — you cannot build this on macOS, Debian, or in a
non-Alpine container. Output defaults to `$HOME/iso-out`.

## Where it builds

| VM | Node | Role |
|---|---|---|
| 200 `th-builder` | px-main | Alpine cloud image, 10 cores / 6 GB. Runs `mkimage`. Exists only to build. |
| 201 `th-test` | px-slow | Boots the ISO and installs it, exactly like a student laptop. Nested virt on. |

The VMs sit on 10.0.5.0/24, which is not routable from a workstation, so SSH
goes through the node that hosts the VM:

```sh
ssh -J root@px-main root@10.0.5.170     # builder
```

Nothing is ever installed on the Proxmox nodes themselves. They host the VMs
and act as a jump host, nothing more.

## Configuration

Both scripts read everything from the environment, so you can point them
somewhere else without editing anything.

`build-on-vm.sh`:

| Variable | Default | What |
|---|---|---|
| `NODE` | `px-main` | Proxmox node, used only as an SSH jump host |
| `BUILDER` | `10.0.5.170` | The builder VM's address |
| `BUILDER_USER` | `root` | User on the builder |
| `ISO_STORE` | `/mnt/pve/cephfs/template/iso` | Where the finished ISO is published. On cephfs, so any node can attach it |

`build.sh`:

| Variable | Default | What |
|---|---|---|
| `ALPINE_BRANCH` | `master` | aports branch to build from |
| `ALPINE_TAG` | `edge` | Alpine release tag |
| `MIRROR` | `https://dl-cdn.alpinelinux.org/alpine` | Package mirror |
| `TH_DEV_KEY` | unset | Path to an SSH pubkey. **Enables sshd on the live ISO.** Debugging only — never ship an image built with this |

### Why edge and not 3.23-stable

The built-in scrolling layout landed in Hyprland 0.54; 3.23 is pinned at
0.51.1. Tracking edge is safe here because each ISO bakes its own package set
into a frozen offline repo — students never track a rolling release. To go
back:

```sh
ALPINE_BRANCH=3.23-stable ALPINE_TAG=v3.23 ./iso/build.sh
```

## What each file does

| File | What |
|---|---|
| `build-on-vm.sh` | Workstation-side driver. Ships source, builds remotely, fetches and publishes the ISO |
| `build.sh` | The actual build. Installs deps, clones aports, runs `mkimage`, collects the image |
| `mkimg.techhorizons.sh` | The Alpine `mkimage` profile: boot menu, volume label, initramfs features, package set |
| `genapkovl-techhorizons.sh` | Builds the apkovl — the overlay that configures the live installer environment |
| `packages.list` | **Single source of truth** for what gets baked into the offline repo |

### Adding a package

Add it to `packages.list` and rebuild. Comments and blank lines are stripped,
and the name must exist in Alpine `main` or `community` for your tag — a typo
fails the build partway through `mkimage` with an apk resolution error, not up
front.

## Gotchas

These all cost real debugging time at least once.

**`mkimage` runs as the unprivileged `build` user.** It cannot traverse a 0700
`/root`. Both the source tree and the output are staged into build-owned
directories under `/home/build` and copied out afterwards. If you add a step
that reads from `/root`, it will fail for this reason and the error will not
say so.

**The stage directory is cleared every run.** `mkimage` does not remove old
images, so a stale ISO from a previous tag gets copied out alongside the new
one and the two are genuinely hard to tell apart.

**`initfs_features` must list every driver class needed to mount the boot
media**, not just to run the system. Omitting `cdrom`/`ata`/`scsi`/`virtio`
produces "Mounting boot media failed" — the kernel boots fine and then the
initramfs cannot mount the ISO it just came from.

**Do not run two builds at once.** Two concurrent `mkimage` runs each spawn
their own `update-kernel` and fight for the same cores. It does not fail, it
just takes far longer than either would alone. Check first:

```sh
ssh -J root@px-main root@10.0.5.170 'pgrep -af "build.sh|mkimage.sh"'
```

**`qm shutdown` does not reliably stop the builder** even though `acpid` is
running in the guest. Power it off from inside instead:

```sh
ssh -J root@px-main root@10.0.5.170 poweroff
```

**Expect a long build.** It pulls ~53 packages including Chromium and builds
an initramfs per kernel flavor.

## Testing the result

Attach the ISO to VM 201 `th-test` and boot it. That VM has nested virt
enabled on purpose — the installed OS must itself run KVM guests, so a test
that skips nested virt does not prove the thing works.

`build-on-vm.sh` already publishes to `ISO_STORE` on cephfs, so the image is
visible from any node in the cluster without copying it again.
