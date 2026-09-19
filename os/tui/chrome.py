"""Shared terminal chrome: the two rails every Tech Horizons TUI screen has.

From the design system, section 07 — Terminal:

    "Keybind hints live on a bottom rail and never move."

So the rail is part of the frame, not something a screen opts into. Both rails
are dim sage on the slightly-raised surface; the body between them owns the
only sage and coral on the screen.

Header reads `th │ <context>` on the left with a status on the right — the
design shows `esc quit`, `step 2/4` and a clock in that slot.
"""
from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

from banner import Banner


POWER_HELPER = "/opt/techhorizons/desktop/power.sh"


class RailTop(Horizontal):
    """`th │ sign in` ......................................... `step 2/4`"""

    def __init__(self, context: str, status: str = "") -> None:
        super().__init__(id="rail-top")
        # NOTE the rail_ prefix: Textual's MessagePump already has a private
        # _context() method, and assigning self._context here shadows it with a
        # string, so the widget's message pump dies with
        # "'str' object is not callable" and the whole app hangs on mount.
        self.rail_context = context
        self.rail_status = status

    def compose(self) -> ComposeResult:
        yield Static(f"th │ {self.rail_context}", id="rail-top-left")
        yield Static(self.rail_status, id="rail-top-right")

    def set_status(self, status: str) -> None:
        self.query_one("#rail-top-right", Static).update(status)


class RailBottom(Static):
    """The keybind rail. Pass (key, label) pairs in the order they should read."""

    def __init__(self, hints: list[tuple[str, str]]) -> None:
        super().__init__(self._render_hints(hints), id="rail-bottom")

    @staticmethod
    def _render_hints(hints: list[tuple[str, str]]) -> str:
        # Three spaces between pairs, matching the spacing in the design.
        return "   ".join(f"{key} {label}" for key, label in hints)

    def set_hints(self, hints: list[tuple[str, str]]) -> None:
        self.update(self._render_hints(hints))


def kv_table(rows: list[tuple[str, str]], key_width: int = 14) -> str:
    """The Field/Value table from the sign-in screen, as markup.

    Keys are dim, values sage -- chrome versus content, per the three signals.
    """
    out = [f"[#DBE4C6 45%]{'Field':<{key_width}}Value[/]", ""]
    for k, v in rows:
        out.append(f"[#DBE4C6 45%]{k:<{key_width}}[/][#DBE4C6]{v}[/]")
    return "\n".join(out)


def check_line(ok: bool, text: str) -> str:
    """A validation line: coral mark plus sage text, never coral prose.

    ok   -> dim tick, dim text (a satisfied rule is chrome, not news)
    warn -> coral bang, sage text (the one thing worth reading)
    """
    if ok:
        return f"[#DBE4C6 45%]✓  {text}[/]"
    return f"[#FF6846]!  [/][#DBE4C6]{text}[/]"


class Repainting:
    """Redraw every cell on a timer.

    Something clears the terminal shortly after the first frame -- it is not a
    resize, the pty never changes size, and chasing it through the compositor,
    the window manager and foot's own startup cost most of a day. Textual then
    re-emits only what it believes changed, and it believes the static parts
    are still on screen when the terminal has already cleared them: rails, box
    borders, labels, the tab row on a panel. What is left looks like a
    half-drawn app.

    Rather than find the clear, recover from it. Marking the whole screen
    region dirty is what makes the next frame a full update -- refresh() alone
    does not, which is why an earlier attempt at this did nothing. Screens that
    are idle by nature can afford it every couple of seconds.

    Mix in BEFORE App and call start_repainting() from on_mount.
    """

    REPAINT_EVERY = 2.0

    def start_repainting(self) -> None:
        self.set_interval(self.REPAINT_EVERY, self._full_repaint)

    def _full_repaint(self) -> None:
        screen = self.screen
        if screen is None:
            return
        try:
            screen._compositor._dirty_regions.add(screen.region)
        except AttributeError:  # private API; degrade to a partial repaint
            pass
        self.refresh(repaint=True, layout=True)

    def on_resize(self) -> None:
        self._full_repaint()


class AuthApp(Repainting, App):
    """The frame both auth screens wear: sign in (greetd) and locked.

    From the design system:

        "The lock box sits centred in the lower third so an animated
         background can run in the field above it without ever being covered.
         Radius drops to 6px."

    So the banner owns the top two thirds and animates the whole way across;
    the box floats in the lower third. `border: round` is the only radius a
    character grid can express, which is what the 6px maps to.

    Subclasses set CONTEXT (the `th │ ...` slot) and implement submit().
    """

    CSS_PATH = "theme.tcss"
    HINTS = [("↵", "unlock")]

    CONTEXT = "sign in"

    # Both screens offer Restart and Shut down, because they are the same
    # screen with a different backend and a student should not have to know
    # which one they are looking at. It matters most here, in fact: a Field
    # Node sitting at the sign-in screen is one somebody wants to turn OFF, and
    # without this the only way is to hold the power button.

    def compose(self) -> ComposeResult:
        yield RailTop(self.CONTEXT, self.status_text())
        yield Banner(id="field")
        with Vertical(id="lower"):
            with Vertical(id="authbox"):
                yield Static(node_name(), id="node")
                yield Static("password", id="pw-label", classes="dim")
                yield Input(password=True, id="pw")
                yield Static("", id="error", classes="check-warn")
                with Horizontal(id="power"):
                    yield Button("Restart", id="restart", classes="-ghost")
                    yield Button("Shut down", id="shutdown", classes="-ghost")
        yield RailBottom(self.HINTS)

    def status_text(self) -> str:
        return ""

    def on_mount(self) -> None:
        self.query_one("#error", Static).display = False
        self.query_one("#pw", Input).focus()
        self.start_repainting()

    # NOTE the press_ prefix. Textual's App already has a private _shutdown()
    # that run_test awaits, and a handler named _shutdown replaces it with a
    # method returning None -- every test then dies with "'NoneType' object
    # can't be awaited". Same trap as _context on RailTop.
    @on(Button.Pressed, "#restart")
    def press_restart(self) -> None:
        self.power("reboot", "restart")

    # NOTE the press_ prefix. Textual's App already has a private _shutdown()
    # that run_test awaits, and a handler named _shutdown replaces it with a
    # method returning None -- every test then dies with "'NoneType' object
    # can't be awaited". Same trap as _context on RailTop.
    @on(Button.Pressed, "#shutdown")
    def press_shutdown(self) -> None:
        self.power("poweroff", "shut down")

    def power(self, action: str, verb: str) -> None:
        """Hand off to the root helper.

        The session is not root and cannot reboot itself -- that is what made
        these two buttons do nothing at all. desktop/power.sh runs under one
        doas rule that permits this script and nothing else.
        """
        self.fail(f"{verb}ing…")
        for b in self.query(Button):
            b.disabled = True
        self.power_worker(action, verb)

    # In a thread: the old version slept on the event loop, so "restarting…"
    # never actually painted and a slow machine looked like a dead button.
    @work(thread=True)
    def power_worker(self, action: str, verb: str) -> None:
        try:
            subprocess.run(["doas", POWER_HELPER, action],
                           capture_output=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            pass
        time.sleep(6)
        self.call_from_thread(self.power_failed, verb)

    def power_failed(self, verb: str) -> None:
        self.fail(f"could not {verb} — hold the power button")
        for b in self.query(Button):
            b.disabled = False

    def take_password(self) -> str:
        field = self.query_one("#pw", Input)
        password = field.value
        field.value = ""
        return password

    @on(Input.Submitted, "#pw")
    def _submitted(self) -> None:
        self.submit()

    def submit(self) -> None:  # pragma: no cover - subclass responsibility
        raise NotImplementedError

    def fail(self, message: str) -> None:
        box = self.query_one("#error", Static)
        box.update(check_line(False, message))
        box.display = True
        self.query_one("#pw", Input).focus()


def node_name() -> str:
    """This field node's name, as the student chose it during setup."""
    try:
        name = Path("/etc/hostname").read_text().strip()
        if name:
            return name
    except OSError:
        pass
    return socket.gethostname() or "field node"
