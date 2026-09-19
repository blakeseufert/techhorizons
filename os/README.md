# Tech Horizons OS

A minimal Alpine Linux ISO that turns a recycled x86_64 laptop into a student's
server (Field Node) *and* their course home.

Students in the Tech Horizons program work from a Pelican case: a
cable they crimp themselves, a laptop running this OS, and a Mikrotik hAP lite.
They set up real domains, run real VMs, deploy real Docker. Nothing is simulated.

This OS exists to get the course done — and to make a decade-old laptop feel
like a deliberate, premium tool rather than e-waste.

## Status
**The ISO builds, installs and boots.** Verified end to end on a Proxmox VM
from a wiped disk, with no manual steps:

| | |
|---|---|
| ISO builds | 1.2 GB, 605-package signed offline repo |
| Boots to installer | full-screen terminal wizard, no shell, no desktop |
| Disk detection | correct on real hardware; install media and <32 GB disks refused |
| Installs | partitions (UEFI + BIOS), formats, 570 packages **with no network** |
| Boots from disk | hostname, timezone and account all as entered in the installer |
| Server stack | Docker and libvirtd start on boot |


## Design rules
- **On rails.** No file manager, no settings app, no workspaces, no stray windows.
- **Offline first.** Students have no internet until the networking stage. The OS
  must be fully usable before that.
- **One toolkit.** Every screen is HTML/CSS in Chromium, backed by one local
  Python service. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Open source.** Course content lives in a public repo and syncs down to each
  student's machine.

## Repo layout
| Path | What |
|---|---|
| `iso/` | Alpine `mkimage` profile — builds the installable ISO |
| `installer/` | Server name, password, timezone, disk. Kiosk UI |
| `greeter/` | Login screen with the Tech Horizons animation |
| `wizard/` | First boot: cable → Mikrotik → join a class |
| `desktop/` | Hyprland + Waybar config |
| `hub/` | Local service: VMs, Docker app store, evidence, course sync |
| `course/` | Course markdown (placeholder content for now) |

## Building
Built and tested on a Proxmox cluster, never on a workstation.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
