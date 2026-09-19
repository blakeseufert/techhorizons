"""Password checking for the lock screen.

The lock screen runs as the student, so it cannot read /etc/shadow. It shells
out to `su` inside a pty instead, which puts the check through PAM exactly as
a real login would -- no shadow access, no setuid helper, no hand-rolled
crypto.

The login screen does NOT use this: it talks to greetd, which does the
authentication itself.
"""
from __future__ import annotations

import os
import pty
import select
import time


def verify(username: str, password: str, timeout: float = 8.0) -> bool:
    """True if `password` is correct for `username`."""
    if not password:
        return False
    pid, fd = pty.fork()
    if pid == 0:
        # child: ask su to do nothing at all, successfully
        os.environ["LC_ALL"] = "C"
        try:
            os.execvp("su", ["su", username, "-c", "true"])
        except OSError:
            os._exit(127)

    sent = False
    deadline = time.time() + timeout
    buf = b""
    try:
        while time.time() < deadline:
            r, _, _ = select.select([fd], [], [], 0.2)
            if r:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                if not sent and b"assword" in buf.lower():
                    os.write(fd, password.encode() + b"\n")
                    sent = True
            if not select.select([fd], [], [], 0)[0]:
                pid_done, status = os.waitpid(pid, os.WNOHANG)
                if pid_done:
                    return os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    finally:
        try:
            os.close(fd)
        except OSError:
            pass

    try:
        os.kill(pid, 9)
    except ProcessLookupError:
        pass
    try:
        _, status = os.waitpid(pid, 0)
        return os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    except ChildProcessError:
        return False
