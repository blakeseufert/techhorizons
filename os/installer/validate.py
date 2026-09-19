"""Input rules for the installer, kept apart from the UI so they can be tested.

The disk rules are the ones that matter: a student who wipes the USB they
booted from loses the session, and one who installs onto a 16GB eMMC cannot
run the VMs the course needs.
"""
from __future__ import annotations

import re

NAME_RE = re.compile(r"^[a-zA-Z0-9-]{1,63}$")
MIN_PASSWORD = 6


def check_name(name: str) -> str | None:
    name = (name or "").strip()
    if not name:
        return "Give your Field Node a name."
    if not NAME_RE.match(name):
        return "Use only letters, numbers and hyphens."
    if name.startswith("-") or name.endswith("-"):
        return "It cannot start or end with a hyphen."
    return None


def check_password(pw: str, confirm: str) -> str | None:
    if len(pw or "") < MIN_PASSWORD:
        return f"Your password needs at least {MIN_PASSWORD} characters."
    if pw != confirm:
        return "The two passwords do not match."
    return None


def check_disk(path: str | None, selectable: list[dict]) -> str | None:
    """`selectable` must already exclude the install media and small disks."""
    if not path:
        return "Choose a disk to install onto."
    if not any(d["path"] == path for d in selectable):
        return "That disk cannot be used. Pick one from the list."
    return None
