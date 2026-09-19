# Building the Tech Horizons ISO

This directory builds `TechHorizonsOS-<tag>-x86_64.iso` — a ~1.3 GB Alpine
image that boots straight into a Chromium-kiosk installer and installs the
whole OS **with no network**.

If you are picking this up cold: you need an Alpine x86_64 machine to build on,
then `BUILDER=<its address> ./iso/build-on-vm.sh`. Everything below is detail
for when that is not enough.

## The one constraint that shapes everything

**Students have no internet until the networking stage of the course.** So the
installer cannot download anything. Every package the installed system will
ever need is baked into an offline apk repo inside the ISO at build time. That
is why the image is 1.3 GB, why `packages.list` matters so much, and why the
build needs a signing key even though nothing is published.

## You need an Alpine builder

`mkimage` needs `apk-tools` and `abuild` running natively. **You cannot build
this on macOS, on Debian/Ubuntu, or in a non-Alpine container.** A throwaway
Alpine VM is the normal answer:

1. Boot the [Alpine cloud image](https://alpinelinux.org/cloud/) (x86_64) on
   whatever hypervisor you have. The reference deployment uses Proxmox; nothing
   about the build cares.
2. Give it **6+ cores and 6 GB RAM**. Cores matter most — the build compiles an
   initramfs per kernel flavour. 40 GB of disk is plenty.
3. Make sure you can SSH in as a user who can run the build as root.

That VM exists only to build. Nothing is installed on the hypervisor itself.

## Two ways to build

### From your workstation (normal path)

```sh
BUILDER=10.0.0.5 ./iso/build-on-vm.sh
```

Ships the source to the builder over SSH, builds there, and pulls the ISO back
into `out/`.

### On the Alpine host directly

```sh
./iso/build.sh [outdir]
```

Must run **as root, on Alpine x86_64**. Output defaults to `$HOME/iso-out`.

## Configuration

Every script reads its settings from the environment. Rather than exporting
them each time, put them in **`th.env` at the repo root** — it is gitignored,
so your own addresses never land in the repo:

```sh
# th.env
BUILDER=10.0.0.5
JUMP=root@hypervisor.example
ISO_STORE=root@hypervisor.example:/var/lib/vz/template/iso
```

### `iso/build-on-vm.sh`

| Variable | Default | What |
|---|---|---|
| `BUILDER` | **required** | Builder host — address, hostname or ssh alias |
| `BUILDER_USER` | `root` | Login on the builder |
| `JUMP` | unset | Optional `ssh -J` jump host, if the builder is on a network you cannot reach directly |
| `ISO_STORE` | unset | Optional scp destination for the finished ISO, e.g. `user@nas:/srv/iso`. Skipped when unset |

### `iso/build.sh`

| Variable | Default | What |
|---|---|---|
| `ALPINE_BRANCH` | `master` | aports branch to build from |
| `ALPINE_TAG` | `edge` | Alpine release tag |
| `MIRROR` | `https://dl-cdn.alpinelinux.org/alpine` | Package mirror |
| `TH_DEV_KEY` | unset | Path to an SSH pubkey. **Enables sshd on the live ISO.** Debugging only — never ship an image built with this |

### `dev/` helpers

| Variable | Used by | What |
|---|---|---|
| `TH_NODE` | `push.sh`, `vm.sh` | Address of a running field node |
| `TH_JUMP` | `push.sh` | Optional jump host to reach it |
| `TH_HOST` | `vm.sh` | Host running `qm` — **Proxmox-specific** |
| `TH_VMID` | `vm.sh` | The test VM's id |

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
| `build-on-vm.sh` | Workstation-side driver. Ships source, builds remotely, fetches the ISO |
| `build.sh` | The actual build. Installs deps, clones aports, runs `mkimage`, collects the image |
| `mkimg.techhorizons.sh` | The Alpine `mkimage` profile: boot menu, volume label, initramfs features, package set |
| `genapkovl-techhorizons.sh` | Builds the apkovl — the overlay that configures the live installer environment |
| `packages.list` | **Single source of truth** for what gets baked into the offline repo |

### Adding a package

Add it to `packages.list` and rebuild. Comments and blank lines are stripped,
and the name must exist in Alpine `main` or `community` for your tag — a typo
fails partway through `mkimage` with an apk resolution error, not up front.

## Gotchas

These each cost real debugging time at least once.

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
ssh "$BUILDER" 'pgrep -af "build.sh|mkimage.sh"'
```

**An apostrophe inside `${VAR:?message}` breaks the script.** Bash reads it as
an opening quote even inside double quotes, and the error points at the end of
the file rather than the line. Keep `:?` messages apostrophe-free.

**On Proxmox, `qm shutdown` may not stop the builder** even with `acpid`
running in the guest. Power it off from inside instead:

```sh
ssh "$BUILDER" poweroff
```

**Expect a long build.** It pulls ~53 packages including Chromium and builds an
initramfs per kernel flavour.

## Testing the result

Boot the ISO on a second VM with **nested virtualisation enabled** — the
installed OS must itself run KVM guests, so a test without nested virt does not
prove the thing works. Install to a blank disk of at least 32 GB; the installer
refuses anything smaller, and refuses the install media itself.
