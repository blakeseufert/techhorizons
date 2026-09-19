#!/usr/bin/env python3
"""Tech Horizons sign-in screen — greetd's greeter.

Wears the shared AuthApp frame: `th │ sign in` on the top rail, the animated
wordmark filling the field above, the box in the lower third. No web stack
until after the session starts.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "greeter"))
from chrome import AuthApp, node_name  # noqa: E402
from greetd_ipc import Greetd, GreetdError  # noqa: E402

SESSION_CMD = os.environ.get(
    "TH_SESSION_CMD", "/opt/techhorizons/desktop/session.sh")


class Greeter(AuthApp):
    TITLE = "Tech Horizons"
    CONTEXT = "sign in"
    # "unlock" is the lock screen's word. This screen signs in.
    HINTS = [("↵", "sign in")]

    def submit(self) -> None:
        password = self.take_password()
        if not password:
            return self.fail("enter your password")
        greetd = None
        try:
            greetd = Greetd()
            greetd.login(node_name(), password)
            greetd.start([SESSION_CMD])
            return  # greetd replaces us with the session
        except GreetdError as exc:
            if greetd:
                greetd.close()
            self.fail("that password is not right" if exc.auth else str(exc))
        except OSError as exc:
            self.fail(f"login service: {exc}")


if __name__ == "__main__":
    Greeter().run()
