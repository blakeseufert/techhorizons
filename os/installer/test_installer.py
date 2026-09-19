#!/usr/bin/env python3
"""Self-check for the installer's guard rails.
Run: python3 installer/test_installer.py

The thing worth protecting is that we never offer, or accept, the disk the
student booted from -- and that a typo cannot reach a real disk.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["TH_FAKE_DISKS"] = "1"

import disks  # noqa: E402
import validate  # noqa: E402

all_disks = disks.list_disks()
ok = disks.selectable(all_disks)

# The 16 GB boot stick must never be selectable -- both because it is the
# install media and because it is under the 32 GB floor.
assert [d["path"] for d in ok] == ["/dev/nvme0n1", "/dev/sda"], ok
media = next(d for d in all_disks if d["path"] == "/dev/sdb")
assert media["is_install_media"] and media["too_small"]

assert disks._human(500 * 1024**3) == "500.0 GB"
assert disks._human(0) == "0 B"

# --- names ---
assert validate.check_name("orion") is None
assert validate.check_name("field-node-1") is None
assert "name" in validate.check_name("").lower()
assert "letters" in validate.check_name("bad name!")
assert "hyphen" in validate.check_name("-nope")
assert "hyphen" in validate.check_name("nope-")
assert validate.check_name("x" * 64) is not None

# --- passwords ---
assert validate.check_password("horizons123", "horizons123") is None
assert "6 characters" in validate.check_password("123", "123")
assert "do not match" in validate.check_password("horizons123", "different")

# --- disks: the security-relevant rules ---
assert validate.check_disk("/dev/sda", ok) is None
assert validate.check_disk(None, ok), "no disk chosen must fail"
assert validate.check_disk("/dev/sdb", ok), "boot media must never be accepted"
assert validate.check_disk("/dev/nope", ok), "unknown disk must never be accepted"

print("all installer checks passed")
