#!/usr/bin/env python3
"""Tech Horizons setup — terminal UI.

Built to the Claude Design project, section 07 — Terminal. Every screen is the
same frame: `th │ <context>` rail on top, body, keybind rail on the bottom that
never moves. Sage for content, dim sage for chrome, coral only for whatever the
cursor is on.

Mouse and keyboard both work -- the users are twelve-year-olds who have never
met a terminal, so nothing may depend on knowing a shortcut.

The machine is a "Field Node" here. The course still calls it a server, which
is the real word for the role.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.message import Message
from textual.widgets import Button, Input, ProgressBar, RadioButton, RadioSet, Static

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "installer"))

import disks as diskmod      # noqa: E402
import validate              # noqa: E402
from chrome import RailBottom, RailTop, check_line, kv_table  # noqa: E402

DEFAULT_TZ = "Australia/Melbourne"
TIMEZONES = [
    "Australia/Melbourne", "Australia/Sydney", "Australia/Brisbane",
    "Australia/Adelaide", "Australia/Perth", "Australia/Hobart",
    "Australia/Darwin", "Pacific/Auckland", "UTC",
]
TOTAL_STEPS = 5


class Choices(RadioSet):
    """A RadioSet where enter means "this one, and on to the next step".

    Stock RadioSet binds enter to ticking the highlighted row and stops there,
    so on a screen that opens with a row already ticked, enter looked broken
    while the bottom rail promised "↵ next". Arrows still move the highlight
    without choosing, and space still ticks without advancing.
    """

    BINDINGS = [("space", "tick", "choose")]

    class Chosen(Message):
        """Enter was pressed on a choice list."""

    def action_tick(self) -> None:
        super().action_toggle_button()

    def action_toggle_button(self) -> None:
        super().action_toggle_button()
        self.post_message(self.Chosen())


class Step(Screen):
    """The shared frame. Subclasses fill in `body()` and `advance()`."""

    CONTEXT = "setup"
    INDEX = 1
    PROMPT = ""
    HINT = ""
    HINTS: list[tuple[str, str]] = [("↵", "next"), ("^B", "back")]

    BINDINGS = [
        ("ctrl+b", "back", "back"),
        ("escape", "back", "back"),
    ]

    def compose(self) -> ComposeResult:
        yield RailTop(self.CONTEXT, f"step {self.INDEX}/{TOTAL_STEPS}")
        with Vertical(id="body"):
            yield Static(self.PROMPT, id="prompt")
            yield Static(self.HINT, id="hint")
            yield from self.body()
        yield RailBottom(self.HINTS)

    def body(self) -> ComposeResult:
        return iter(())

    def on_mount(self) -> None:
        for w in self.query(Input):
            w.focus(); return
        for w in self.query(RadioSet):
            w.focus(); return
        # A screen that is all buttons -- the finished screen -- used to focus
        # nothing at all, so enter went nowhere while the rail said
        # "↵ restart now".
        for w in self.query("#next"):
            w.focus(); return

    def fail(self, message: str) -> None:
        """Validation shows as a rail-consistent line, not a popup."""
        self.query_one("#hint", Static).update(f"[#FF6846]! [/][#DBE4C6]{message}[/]")

    def action_back(self) -> None:
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()

    @on(Button.Pressed, "#next")
    def _next(self) -> None:
        self.advance()

    @on(Button.Pressed, "#back")
    def _back(self) -> None:
        self.action_back()

    @on(Choices.Chosen)
    def _chosen(self) -> None:
        self.advance()

    @on(Input.Submitted)
    def _submitted(self, event: Input.Submitted) -> None:
        # Enter in a field that is not the last one moves to the next field
        # rather than submitting the step. On the password screen a student
        # types the password, hits enter, types it again -- and without this
        # both go into the first box and the step fails on a mismatch that
        # never happened.
        fields = list(self.query(Input))
        i = fields.index(event.input)
        if i + 1 < len(fields):
            fields[i + 1].focus()
            return
        self.advance()

    def advance(self) -> None:
        raise NotImplementedError


class NameStep(Step):
    CONTEXT = "node create"
    INDEX = 1
    PROMPT = "Name this field node"
    HINT = "letters, numbers and hyphens · 1–63 characters"
    HINTS = [("↵", "next")]

    def body(self) -> ComposeResult:
        yield Input(placeholder="orion", id="name")
        yield Static("", id="checks")
        yield Static("", id="resolves", classes="dim")
        with Horizontal(id="buttons"):
            yield Button("Continue", id="next", classes="-primary")

    @on(Input.Changed, "#name")
    def _live(self, event: Input.Changed) -> None:
        """Live validation, in the design's mark-plus-text form."""
        name = event.value.strip()
        checks = self.query_one("#checks", Static)
        resolves = self.query_one("#resolves", Static)
        if not name:
            checks.update("")
            resolves.update("")
            return
        err = validate.check_name(name)
        lines = [
            check_line(bool(name) and err is None,
                       f"name ok — {len(name)} characters" if err is None else err),
        ]
        checks.update("\n".join(lines))
        resolves.update(
            f"[#DBE4C6 45%]resolves to [/][#DBE4C6]{name.lower()}[/]" if err is None else "")

    def advance(self) -> None:
        name = self.query_one("#name", Input).value.strip()
        if (err := validate.check_name(name)):
            return self.fail(err)
        # The live check promised "resolves to orion"; keep that promise. The
        # name becomes the hostname AND the login, and a mixed-case login is a
        # password-that-is-not-wrong bug waiting for a student.
        self.app.cfg["server_name"] = name.lower()
        self.app.push_screen(PasswordStep())


class PasswordStep(Step):
    CONTEXT = "node create"
    INDEX = 2
    PROMPT = "Set a password"
    HINT = "you will use this to log in · nobody can recover it for you"

    def body(self) -> ComposeResult:
        yield Input(password=True, placeholder="password", id="pw")
        yield Input(password=True, placeholder="again", id="pw2")
        yield Static("", id="checks")
        with Horizontal(id="buttons"):
            yield Button("Continue", id="next", classes="-primary")
            yield Button("Back", id="back", classes="-ghost")

    @on(Input.Changed)
    def _live(self) -> None:
        pw = self.query_one("#pw", Input).value
        pw2 = self.query_one("#pw2", Input).value
        checks = self.query_one("#checks", Static)
        if not pw:
            checks.update(""); return
        lines = [check_line(len(pw) >= validate.MIN_PASSWORD,
                            f"at least {validate.MIN_PASSWORD} characters")]
        if pw2:
            lines.append(check_line(pw == pw2, "both entries match"))
        checks.update("\n".join(lines))

    def advance(self) -> None:
        pw = self.query_one("#pw", Input).value
        pw2 = self.query_one("#pw2", Input).value
        if (err := validate.check_password(pw, pw2)):
            return self.fail(err)
        self.app.cfg["password"] = pw
        self.app.push_screen(RegionStep())


class RegionStep(Step):
    CONTEXT = "node create"
    INDEX = 3
    PROMPT = "Where is this node?"
    HINT = "sets the clock · logs and scheduled tasks depend on it"
    HINTS = [("↕", "choose"), ("↵", "next"), ("^B", "back")]

    def body(self) -> ComposeResult:
        with Choices(id="tz"):
            for tz in TIMEZONES:
                yield RadioButton(tz, value=(tz == DEFAULT_TZ))
        with Horizontal(id="buttons"):
            yield Button("Continue", id="next", classes="-primary")
            yield Button("Back", id="back", classes="-ghost")

    def advance(self) -> None:
        rs = self.query_one("#tz", Choices)
        self.app.cfg["timezone"] = (
            rs.pressed_button.label.plain if rs.pressed_button else DEFAULT_TZ)
        self.app.push_screen(DiskStep())


class DiskStep(Step):
    CONTEXT = "node create"
    INDEX = 4
    PROMPT = "Choose a disk"
    HINT = "everything on the disk you pick will be erased"
    HINTS = [("↕", "choose"), ("↵", "next"), ("^B", "back")]

    def body(self) -> ComposeResult:
        every = diskmod.list_disks()
        self.disks = diskmod.selectable(every)
        self.excluded = [d for d in every if d not in self.disks]
        if self.disks:
            with Choices(id="disk"):
                for i, d in enumerate(self.disks):
                    yield RadioButton(
                        # ~74 columns fit inside the list box on a 1280px
                        # screen; keep the whole "now:" phrase inside that.
                        f"{d['size_h']:>9}  {d['kind']:<9}  {d['model'][:16]:<16}"
                        f"  now: {d['existing'][:27]}",
                        value=(i == 0))
        else:
            yield Static("No usable disk. This machine needs a 32 GB or larger "
                         "drive to run the course.", classes="sage")
        if self.excluded:
            yield Static("\n".join(
                check_line(False,
                           f"{d['path']} — " + ("the drive you booted from"
                           if d["is_install_media"] else "too small (needs 32 GB)"))
                for d in self.excluded), id="checks")
        with Horizontal(id="buttons"):
            yield Button("Continue", id="next", classes="-primary")
            yield Button("Back", id="back", classes="-ghost")

    def advance(self) -> None:
        if not self.disks:
            return self.fail("There is no disk this can be installed onto.")
        rs = self.query_one("#disk", Choices)
        idx = rs.pressed_index if rs.pressed_index >= 0 else 0
        d = self.disks[idx]
        self.app.cfg["disk"] = d["path"]
        # For the confirm screen: "/dev/sda" tells a student nothing, the
        # size and model are what they picked it by.
        self.app.cfg["disk_label"] = f"{d['size_h']} {d['kind']} · {d['model']}"
        self.app.push_screen(ConfirmStep())


class ConfirmStep(Step):
    CONTEXT = "node create"
    INDEX = 5
    PROMPT = "Does this look right?"
    HINT = ""
    HINTS = [("↔", "toggle"), ("↵", "submit"), ("^B", "back")]

    def body(self) -> ComposeResult:
        c = self.app.cfg
        yield Static(kv_table([
            ("Field node", c.get("server_name", "")),
            ("Region",     c.get("timezone", "")),
            ("Disk",       c.get("disk_label") or c.get("disk", "")),
            ("Erases",     "everything on that disk"),
        ]), id="kv")
        with Horizontal(id="buttons"):
            yield Button("Yes", id="next", classes="-primary")
            yield Button("No, change it", id="back", classes="-ghost")

    def advance(self) -> None:
        self.app.push_screen(InstallStep())


class InstallStep(Step):
    CONTEXT = "node create"
    INDEX = 5
    PROMPT = "Installing"
    HINT = "this takes a few minutes · leave the laptop plugged in"
    HINTS = [("", "please wait")]
    # No way back from here. The shared frame binds escape and ^B to "back",
    # and on this screen back meant popping to Confirm while install.sh kept
    # running -- so pressing Yes again started a SECOND installer on the same
    # disk. A twelve-year-old pressing escape because nothing seems to be
    # happening is not an edge case. (Textual merges BINDINGS down the class
    # tree, so emptying the list here would not unbind them -- the action does.)
    def action_back(self) -> None:
        pass

    def compose(self) -> ComposeResult:
        yield RailTop(self.CONTEXT, f"step {self.INDEX}/{TOTAL_STEPS}")
        with Vertical(id="body"):
            yield Static(self.PROMPT, id="prompt")
            yield Static(self.HINT, id="hint")
            yield ProgressBar(total=100, show_eta=False, id="bar")
            yield Static("", id="msg", classes="dim")
            with Horizontal(id="buttons"):
                yield Button("Restart", id="next", classes="-primary")
        yield RailBottom(self.HINTS)

    def on_mount(self) -> None:
        btn = self.query_one("#next", Button)
        btn.display = False
        self.run_install()

    def advance(self) -> None:
        if not self.app.finished:
            return
        # The install is already on disk, so the only job left is to get the
        # machine to restart. Ordinary reboot did nothing at all on the live
        # ISO and reported nothing either, so try the managed paths first and
        # fall back to the one that cannot be ignored. Whatever happens, the
        # student gets told.
        subprocess.run(["sync"], check=False)
        attempts = [
            ["openrc-shutdown", "-r", "now"],
            ["/sbin/reboot"],
            ["/bin/busybox", "reboot", "-f"],
        ]
        errors = []
        for cmd in attempts:
            self.query_one("#msg", Static).update(f"[#DBE4C6 45%]{' '.join(cmd)}[/]")
            self.refresh()
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            except (OSError, subprocess.SubprocessError) as exc:
                errors.append(f"{cmd[0]}: {exc}")
                continue
            if r.returncode != 0:
                errors.append(f"{cmd[0]}: {(r.stderr or r.stdout).strip()[:40]}")
                continue
            # It returned cleanly. Give it a moment to actually take the
            # machine down before deciding it lied.
            time.sleep(5)
            errors.append(f"{cmd[0]}: exited 0 but nothing happened")
        self.query_one("#msg", Static).update(
            check_line(False, "restart failed — hold the power button for "
                              "five seconds. " + " · ".join(errors)[:60]))

    @work(thread=True)
    def run_install(self) -> None:
        c = self.app.cfg
        env = dict(os.environ)
        env.update({
            "TH_DISK": c["disk"],
            "TH_HOSTNAME": c["server_name"],
            "TH_PASSWORD": c["password"],
            "TH_TIMEZONE": c.get("timezone", DEFAULT_TZ),
        })
        script = str(HERE.parent / "installer" / "install.sh")
        tail = ""
        try:
            proc = subprocess.Popen(["/bin/sh", script], env=env, text=True,
                                    bufsize=1, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
        except OSError as exc:
            self.app.call_from_thread(self.failed, f"could not start: {exc}")
            return
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line.startswith("PROGRESS "):
                parts = line.split(" ", 2)
                try:
                    pct = int(parts[1])
                except (IndexError, ValueError):
                    continue
                self.app.call_from_thread(
                    self.progress, pct, parts[2] if len(parts) > 2 else "")
            elif line:
                tail = line
        if proc.wait() != 0:
            self.app.call_from_thread(self.failed, tail or "the install failed")
            return
        self.app.call_from_thread(self.done)

    def progress(self, pct: int, msg: str) -> None:
        self.query_one("#bar", ProgressBar).update(progress=pct)
        self.query_one("#msg", Static).update(msg[:78])

    def failed(self, message: str) -> None:
        self.query_one("#prompt", Static).update("Something went wrong")
        self.query_one("#hint", Static).update(f"[#FF6846]! [/][#DBE4C6]{message}[/]")
        self.query_one("#msg", Static).update("")
        btn = self.query_one("#next", Button)
        btn.display = True; btn.focus()
        self.query_one("#rail-bottom", RailBottom).set_hints([("↵", "restart")])
        self.app.finished = True

    def done(self) -> None:
        self.query_one("#bar", ProgressBar).update(progress=100)
        self.query_one("#prompt", Static).update("This field node is ready")
        self.query_one("#hint", Static).update("remove the USB stick, then restart")
        self.query_one("#msg", Static).update("")
        btn = self.query_one("#next", Button)
        btn.label = "Restart now"; btn.display = True; btn.focus()
        self.query_one("#rail-bottom", RailBottom).set_hints([("↵", "restart now")])
        self.app.finished = True


class Setup(App):
    CSS_PATH = "theme.tcss"
    TITLE = "Tech Horizons"

    def __init__(self) -> None:
        super().__init__()
        self.cfg: dict[str, str] = {}
        self.finished = False

    def on_mount(self) -> None:
        self.push_screen(NameStep())

    # There is nothing to cancel TO. On the live ISO this app is the whole
    # machine: Textual's stock ^C shows an off-theme "press ctrl+q to quit"
    # toast, and ^Q then dropped the student onto a bare Alpine login where
    # "root" and enter gave a passwordless shell -- two keypresses from the
    # installer. Both quit paths are swallowed; turning the laptop off is the
    # only way out, which is the right one.
    def action_quit(self) -> None:  # type: ignore[override]
        pass

    def action_help_quit(self) -> None:
        pass


if __name__ == "__main__":
    Setup().run()
