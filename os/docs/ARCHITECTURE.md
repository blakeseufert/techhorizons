# Tech Horizons OS — Architecture

## What this is
A custom Alpine Linux ISO. Installed on a recycled x86_64 laptop, it turns that
laptop into the student's **server** and their **course home** at the same time.
Students run real VMs, real Docker, real domains on it. Everything is on rails.

## Decisions (2026-09-06)

| Decision | Choice | Why |
|---|---|---|
| Base | Alpine Linux (edge/community) | Minimal, appliance-shaped, apk is trivial to pin |
| Compositor | Hyprland | In Alpine community; Omarchy-style tiling feel |
| Bar | **Waybar** (not Quickshell) | Quickshell is not packaged for Alpine and upstream does not support musl |
| All UI surfaces | **Local web apps in `chromium --app=`** | Chromium already ships; one toolkit for sidebar, VM manager, app store, installer, greeter |
| Target hardware | Generic x86_64 UEFI | Chromebook quirks deliberately deferred, not baked in |
| Evidence | Local-first, sync later | Must work offline — students have no internet until the Mikrotik stage |

## The one big idea
Quickshell is gone, so there is no second GUI toolkit. **Every** screen in this OS
is HTML/CSS rendered by Chromium, backed by one local Python service.

    Waybar (top bar, thin)
      └─ buttons toggle chromium --app= windows
           └─ Hyprland window rules pin them (sidebar = 1/4 width, floating)
                └─ all served by th-hub on 127.0.0.1

This means the course sidebar, the VM manager, the app store, the installer and
the greeter are the same skillset and the same design system. On e-waste hardware
that is also the cheapest way to look premium: CSS costs nothing to render.

## Components

- **`iso/`** — Alpine `mkimage` profile. Builds the installable ISO.
- **`tui/`** — Every terminal surface, as one Textual app family sharing
  `theme.tcss`: the setup wizard, the login screen and the lock screen. Mouse
  and keyboard, running in `foot` under `cage`.
- **`installer/`** — The install itself, with no UI: disk discovery, the input
  rules, and `install.sh` which partitions, formats and installs. Driven by
  `tui/install.py`. Refuses to install onto the ISO media.
- **`greeter/`** — What greetd launches (`session.sh`), the terminal config it
  runs in, the banner artwork, and the greetd JSON-over-unix-socket client.
- **`wizard/`** — First-boot, fullscreen: build your cable → set up the Mikrotik
  (or join wifi/LAN to skip) → join a class or continue as guest.
- **`desktop/`** — Hyprland + Waybar config. No workspaces, no file manager, no
  settings app, no floating windows beyond ours.
- **`hub/`** — One Python/FastAPI service on localhost. Serves every web surface
  and owns: libvirt (VMs), Docker (app store), evidence storage, course sync.
- **`course/`** — Dummy markdown content. Real content lands in the public repo
  and is pulled down by `hub`.

## Hard-won boot facts
Things that cost a debugging cycle each, recorded so they are not rediscovered:

- **The boot media is mounted under `/media/<device>`**: `/media/cdrom` for a
  CD or a VM's virtual drive, `/media/sdb1` (or whatever the stick is) on a
  real laptop. Nothing may hard-code the cdrom path: install.sh reads
  `/etc/apk/repositories` (which the initramfs writes) and falls back to
  `/media/*/apks`, and the overlay ships no repositories file of its own. The
  three VM installs that passed before this was found all booted from a CD.
  To test the stick path in the VM, attach the ISO as a raw virtio disk
  (`-drive file=...iso,format=raw -device virtio-blk-pci`); QEMU's emulated
  USB stick hangs in SeaBIOS at the isolinux prompt.
- The boot menu says **"Tech Horizons OS"**, the volume label is
  `TechHorizonsOS` and the file is `TechHorizonsOS-<tag>-x86_64.iso`:
  `iso/mkimg.techhorizons.sh` overrides mkimage's `syslinux_gen_config`,
  `grub_gen_config` and `gen_volid` (it is sourced after mkimg.base.sh, so
  its definitions win) and sets `image_name`.
- The mkimage profile's `$apks` fills the ISO's **offline repo**. The live root
  is built from **`/etc/apk/world`** -- without it the ISO boots empty.
- `initfs_features` must name every driver class needed to mount the ISO's own
  media (`cdrom ata scsi usb virtio`), or the initramfs cannot find itself.
- Alpine's initramfs **only inserts modules named in the `modules=` kernel
  parameter** -- it does not probe. A correct initramfs still fails to mount
  root without it.
- `mkimage` runs as the unprivileged `build` user: anything it reads or writes
  must not sit under a 0700 `/root`.
- cage needs `XDG_RUNTIME_DIR` and a seat. Alpine's libseat has no `builtin`
  backend, so `seatd` is required.
- wlroots enumerates input through **udev**, not busybox `mdev`.
- Only enable an OpenRC service whose package is actually installed; otherwise
  it silently never runs.

### Desktop session facts
- The session needs a **D-Bus session bus** (`dbus-run-session`). Without one
  waybar cannot start at all and never creates its bar.
- waybar's **`pulseaudio` module takes the whole bar down** if no sound server
  is running. Start pipewire and wait for `$XDG_RUNTIME_DIR/pulse/native`
  before launching it. The symptom is no top bar and no obvious reason.
- GTK's CSS parser is stricter than a browser's: `font-variant-numeric` is a
  parse error, and it masks whatever error comes after it.
- **Hyprland window rules must match on `class`, not `title`.** Rules are
  evaluated when a window is mapped; chromium sets its title only after the
  page loads, so a title rule is tested against a title that does not exist
  yet and silently never matches.
- chromium ignores `--class` in `--app` mode; the Wayland app_id is derived
  from the URL as `chrome-<url>-Default`. Our rules depend on that string, so
  moving a surface to th-hub over http changes its class.
- Do not write a broad `tile` rule. It matches the floating surfaces too and,
  being later, silently overrides their float rules.
- busybox `pgrep -f` / `pkill -f` **match their own command line**. Always use
  the bracket form (`[t]h-course`) or a script kills itself.

### Keeping students on the rails
- **Textual's quit keys are live by default.** `ctrl+q` runs `action_quit` and
  `ctrl+c` runs `action_help_quit` (an off-theme "press ctrl+q" toast). On the
  live ISO quitting the wizard dropped to a getty, and the live root has no
  password -- two keypresses from the installer to a root shell. The wizard
  overrides both actions with no-ops; the live overlay ships an `/etc/inittab`
  with no gettys; the installer runs in a `while :` loop.
- **`kb_options = srvrkeys:none`** removes the `XF86Switch_VT_n` keysyms, so
  Ctrl+Alt+Fn does nothing in Hyprland, and `XKB_DEFAULT_OPTIONS=srvrkeys:none`
  does the same for cage (installer, greeter, lock). It closes the only route
  around the lock screen and the "Alt+F4 became Ctrl+Alt+F4, black screen,
  no way back" trap. It also means **there is no console route onto a student
  image** -- dev access is `TH_DEV_KEY` at build time, nothing else.
- **`set -o pipefail`** in install.sh: apk's output goes through a progress
  loop, and without it a failed apk exited the pipeline 0 and the wizard said
  "ready" over an empty root. busybox ash supports it.
- The chromium managed policy is written to the **live** ISO's /etc by the
  overlay; install.sh has to copy `/etc/chromium/policies` onto the target or
  the installed browser is stock. `URLBlocklist` fences `file://` to our own
  pages -- the address bar is real, and `file:///` is a directory listing of
  the whole disk otherwise.
- **NetworkManager asks polkit, and there is no polkit agent.** As installed,
  the student could scan for or join Wi-Fi only with "auth" -- an admin prompt
  nothing on this desktop can show -- so the Wi-Fi tab failed silently at
  home. `desktop/polkit/10-techhorizons-network.rules` grants the plugdev
  group every NetworkManager action; install.sh puts the student in plugdev.
- **The dock panels are Textual apps, not shell scripts.** display.py and
  network.py share `panel/panel.tcss`: controls are Buttons on a `.card`
  surface, the current one filled. The shell version of the display panel
  drew the same thing with escape codes and parsed mouse clicks by hand; it is
  gone. A zoom change moves the panel's own window, or it slides off the
  bottom-right of the newly smaller logical screen with the student's cursor
  on it.
- **The sign-in banner has twenty effects, ten shown per boot.** The first ten
  were one primitive -- a straight glide in flat coral -- which is why they
  read alike. `tui/banner.py` now gives each glyph a polyline of waypoints,
  an ease and a coral-to-sage gradient (fireworks, blackhole, rain, matrix,
  slide, waves, beam, burn, expand, spotlight). Every timing is a multiple of
  `TRAVEL`, which is also what lets the test suite run a whole cycle in a
  blink. It is still not ttfx: ttfx is a CLI that owns a tty, and this has to
  share a Textual screen with the password box.
- Hyprland emits **no focus event for a click on the wallpaper**, only for a
  click on another window. Popup panels close on focus loss (panel.sh watches
  `.socket2.sock`), so clicking the browser dismisses them and clicking empty
  wallpaper does not.

## Deliberate omissions
No file manager, no system settings, no terminal in the launcher, no workspace
switcher, no user-visible package manager. Networking troubleshooting lives next
to the clock and nowhere else.

## Build & test
Everything happens in two VMs. **Nothing is ever installed on the hypervisor
itself** — it hosts the VMs and, where the VMs are not directly reachable, acts
as an SSH jump host. Nothing more.

| VM | Role |
|---|---|
| `th-builder` | Alpine cloud image. Runs `mkimage` and emits the ISO. Exists only to build. 6 cores / 6 GB is comfortable; more cores helps most. |
| `th-test` | Boots the ISO and installs it, exactly like a student laptop. Nested virt on, because the installed OS must itself run KVM guests. |

`mkimage` needs a native Alpine userspace, which is the only reason the builder
exists. Drive the whole thing from a workstation with `iso/build-on-vm.sh`.

Point the scripts at your own hosts with `th.env` at the repo root — it is
gitignored, so your addresses stay out of the repo. See
[iso/README.md](../iso/README.md) for the full list of variables.

The reference deployment runs both VMs on Proxmox, which is why `dev/vm.sh`
drives the test VM through `qm monitor`. Any hypervisor works for building;
only that one dev helper is Proxmox-specific.
