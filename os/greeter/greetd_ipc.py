"""Minimal client for greetd's IPC protocol.

greetd speaks length-prefixed JSON over a unix socket named by $GREETD_SOCK:
a native-endian u32 length followed by the JSON payload.

The login dance is:
    create_session(username)
      -> auth_message(secret, "Password:")   # prompt for the password
    post_auth_message_response(password)
      -> success                              # credentials accepted
    start_session(cmd)                        # greetd replaces us with the session

Nothing here ever logs a password.
"""
from __future__ import annotations

import json
import os
import socket
import struct


class GreetdError(Exception):
    """greetd refused the request. `auth` marks a wrong password rather than a
    protocol or configuration failure, so the UI can say something useful."""

    def __init__(self, message: str, auth: bool = False):
        super().__init__(message)
        self.auth = auth


class Greetd:
    def __init__(self, sock_path: str | None = None):
        path = sock_path or os.environ.get("GREETD_SOCK")
        if not path:
            raise GreetdError("GREETD_SOCK is not set — not running under greetd.")
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.connect(path)

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass

    # -- wire format ---------------------------------------------------
    def _send(self, payload: dict) -> dict:
        raw = json.dumps(payload).encode()
        self._sock.sendall(struct.pack("=I", len(raw)) + raw)
        return self._recv()

    def _recv(self) -> dict:
        header = self._read_exactly(4)
        (length,) = struct.unpack("=I", header)
        return json.loads(self._read_exactly(length).decode())

    def _read_exactly(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise GreetdError("greetd closed the connection.")
            buf += chunk
        return buf

    # -- protocol ------------------------------------------------------
    def login(self, username: str, password: str) -> None:
        """Authenticate. Raises GreetdError(auth=True) on a bad password."""
        reply = self._send({"type": "create_session", "username": username})

        # greetd may ask several questions (PAM decides). Answer secret prompts
        # with the password; acknowledge info prompts with an empty response.
        while reply.get("type") == "auth_message":
            kind = reply.get("auth_message_type")
            if kind == "secret":
                reply = self._send(
                    {"type": "post_auth_message_response", "response": password}
                )
            elif kind in ("visible",):
                reply = self._send(
                    {"type": "post_auth_message_response", "response": username}
                )
            else:  # info / error -- nothing to answer with
                reply = self._send({"type": "post_auth_message_response"})

        if reply.get("type") == "success":
            return

        self.cancel()
        raise GreetdError(
            reply.get("description") or "Login failed.",
            auth=reply.get("error_type") == "auth_error",
        )

    def start(self, cmd: list[str], env: list[str] | None = None) -> None:
        reply = self._send({"type": "start_session", "cmd": cmd, "env": env or []})
        if reply.get("type") != "success":
            raise GreetdError(reply.get("description") or "Could not start the session.")

    def cancel(self) -> None:
        try:
            self._send({"type": "cancel_session"})
        except (OSError, GreetdError):
            pass
