#!/usr/bin/env python3
"""Tech Horizons lock screen.

IMPORTANT -- this is a "soft" lock, chosen deliberately over a real one.
It is a fullscreen terminal that asks for the password before letting the
student back to their desktop. It stops a classmate wandering past. It does
NOT stop the person sitting at the keyboard: they can switch VT or kill the
process from another session and reach the desktop again.

The alternative, waylock, is a genuine unescapable Wayland session lock but
can only paint a flat colour -- no animation, nothing branded. hyprlock, which
could do both, is not packaged for Alpine. Given these are classroom laptops
where the student already owns the login password, matching the sign-in screen
was judged worth more than a lock the owner cannot escape.

If that trade ever stops being right, swap desktop/lock.sh back to waylock.
"""
from __future__ import annotations

import getpass
import sys
import time
from pathlib import Path

from textual import work
from textual.widgets import Input

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from auth import verify  # noqa: E402
from chrome import AuthApp, RailTop  # noqa: E402


class Lock(AuthApp):
    TITLE = "Locked"
    CONTEXT = "locked"

    def status_text(self) -> str:
        # The design puts a clock in the top rail's status slot on this screen.
        return time.strftime("%H:%M")

    def on_mount(self) -> None:
        super().on_mount()
        self.set_interval(20, self.tick)

    def tick(self) -> None:
        self.query_one(RailTop).set_status(self.status_text())

    def submit(self) -> None:
        password = self.take_password()
        if not password:
            return self.fail("enter your password")
        self.query_one("#pw", Input).disabled = True
        self.check(password)

    @work(thread=True)
    def check(self, password: str) -> None:
        ok = verify(getpass.getuser(), password)
        self.call_from_thread(self.result, ok)

    def result(self, ok: bool) -> None:
        self.query_one("#pw", Input).disabled = False
        if ok:
            return self.exit(0)
        self.fail("that password is not right")


if __name__ == "__main__":
    sys.exit(Lock().run() or 0)
