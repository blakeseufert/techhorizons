"""Disk discovery for the installer.

The one rule that matters here: never offer the install media as a target.
A student who wipes the USB they booted from loses the whole session.
"""
from __future__ import annotations

import os
import re
import subprocess

SYS_BLOCK = "/sys/block"

# Whole-disk devices we care about. Excludes loop/ram/zram/dm/md by omission.
_DISK_RE = re.compile(r"^(nvme\d+n\d+|sd[a-z]+|vd[a-z]+|mmcblk\d+|hd[a-z]+)$")


def _read(path: str, default: str = "") -> str:
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return default


def _human(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if nbytes < 1024 or unit == "TB":
            return f"{nbytes:.0f} {unit}" if unit in ("B", "KB") else f"{nbytes:.1f} {unit}"
        nbytes /= 1024.0
    return f"{nbytes:.1f} TB"


def _busy_devices() -> set[str]:
    """Base names of disks backing a live mount -- i.e. the install media.

    /proc/mounts gives us partitions (sdb1); we strip to the parent disk (sdb)
    so the whole stick is excluded, not just the mounted slice.
    """
    busy: set[str] = set()
    for line in _read("/proc/mounts").splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[0].startswith("/dev/"):
            continue
        dev = os.path.basename(parts[0])
        for name in os.listdir(SYS_BLOCK) if os.path.isdir(SYS_BLOCK) else []:
            # sdb1 -> sdb, nvme0n1p2 -> nvme0n1, mmcblk0p1 -> mmcblk0
            if dev == name or dev.startswith(name + "p") or (
                dev.startswith(name) and dev[len(name):].isdigit()
            ):
                busy.add(name)
    return busy


def _kind(name: str) -> str:
    if name.startswith("nvme"):
        return "NVMe SSD"
    if name.startswith("mmcblk"):
        return "eMMC"
    if _read(f"{SYS_BLOCK}/{name}/queue/rotational") == "1":
        return "HDD"
    return "SSD"


def _existing(name: str) -> str:
    """What's on the disk now, so a student can tell 'the Windows one' apart."""
    try:
        out = subprocess.run(
            ["lsblk", "-nro", "FSTYPE,LABEL", f"/dev/{name}"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    seen: list[str] = []
    for line in out.splitlines():
        bits = line.split(maxsplit=1)
        if not bits or bits[0] in ("", "swap"):
            continue
        tag = bits[1] if len(bits) > 1 and bits[1] else bits[0]
        if tag not in seen:
            seen.append(tag)
    # Our own labels read "TH-BOOT, techhorizons" -- to a student doing a
    # reinstall that is noise where "the old one" is the answer.
    if any(t.lower() in ("th-boot", "techhorizons") for t in seen):
        return "Tech Horizons (old install)"
    return ", ".join(seen[:3]) if seen else "empty"


def _fake() -> list[dict]:
    """Dev-only sample set, so the UI can be worked on off-target.
    Enabled with TH_FAKE_DISKS=1; never set on the ISO."""
    raw = [
        ("nvme0n1", "SAMSUNG MZVLB256", "NVMe SSD", 256, "Windows, Recovery", False, False),
        ("sda", "ST500LM012 HN-M5", "HDD", 500, "empty", False, False),
        ("sdb", "SanDisk Ultra", "SSD", 16, "TECHHORIZONS", True, True),
    ]
    return [{
        "name": n, "path": f"/dev/{n}", "model": m, "kind": k,
        "size": gb * 1024**3, "size_h": _human(gb * 1024**3), "existing": e,
        "removable": rm, "is_install_media": media, "too_small": gb < 32,
    } for n, m, k, gb, e, rm, media in raw]


def list_disks() -> list[dict]:
    if os.environ.get("TH_FAKE_DISKS") == "1":
        return _fake()
    if not os.path.isdir(SYS_BLOCK):
        return []
    busy = _busy_devices()
    disks = []
    for name in sorted(os.listdir(SYS_BLOCK)):
        if not _DISK_RE.match(name):
            continue
        # 512-byte sectors regardless of physical block size.
        size = int(_read(f"{SYS_BLOCK}/{name}/size", "0")) * 512
        if size <= 0:
            continue
        removable = _read(f"{SYS_BLOCK}/{name}/removable") == "1"
        model = _read(f"{SYS_BLOCK}/{name}/device/model") or "Unknown"
        disks.append({
            "name": name,
            "path": f"/dev/{name}",
            "model": model,
            "kind": _kind(name),
            "size": size,
            "size_h": _human(size),
            "existing": _existing(name),
            "removable": removable,
            "is_install_media": name in busy,
            # Too small to hold the OS plus the VMs the course requires.
            "too_small": size < 32 * 1024**3,
        })
    return disks


def selectable(disks: list[dict]) -> list[dict]:
    return [d for d in disks if not d["is_install_media"] and not d["too_small"]]


if __name__ == "__main__":
    import json
    print(json.dumps(list_disks(), indent=2))
