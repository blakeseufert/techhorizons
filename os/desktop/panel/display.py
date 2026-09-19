#!/usr/bin/env python3
"""The display panel: make everything bigger or smaller, and the volume.

These are donated laptops with whatever panel they shipped with, and a
fourteen-year-old reading a terminal on a 1366x768 screen is a real problem.
Scaling the output scales the whole desktop -- bar, browser, terminals --
rather than just a font size somewhere.

Hyprland rejects a scale that does not divide the mode into whole pixels, so
offer a short list of ones that do rather than a free slider. Volume lives here
rather than in its own dock pill: one button for "how this machine presents
itself" rather than two.

Same frame as the network panel: the sizes are buttons on a card, the one you
are on is filled. It replaced a shell script that drew the same thing with
escape codes and read clicks by hand.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "tui"))
from chrome import Repainting  # noqa: E402

STEPS = ("1", "1.25", "1.5", "1.75", "2")


def monitor() -> tuple[str, float, str]:
    """(name, scale, mode) of the first output.

    The mode is what we are ALREADY on, never "preferred": on a virtual output
    preferred came back as 800x600, and after a few of those the display got
    stuck there until the session restarted -- which on a student's laptop
    would look exactly like breaking their screen.
    """
    out = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True,
                         text=True, timeout=5).stdout
    m = json.loads(out or "[]")[0]
    return m["name"], float(m["scale"]), "%dx%d@%.5f" % (m["width"], m["height"], m["refreshRate"])


def volume() -> str:
    out = subprocess.run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                         capture_output=True, text=True, timeout=5).stdout.split()
    try:
        pct = f"{float(out[1]) * 100:.0f}%"
    except (IndexError, ValueError):
        return "n/a"
    return "muted" if "[MUTED]" in out else pct


class DisplayPanel(Repainting, App):
    CSS_PATH = "panel.tcss"
    TITLE = "Display"

    BINDINGS = [("escape", "quit", "close"), ("q", "quit", "close")]

    def compose(self) -> ComposeResult:
        yield Static("[#FF6846]Display[/]", id="title")
        yield Static("zoom the whole desktop in or out", classes="dim")
        with Vertical(classes="card"):
            yield Static("Text size", classes="label")
            with Horizontal(id="sizes"):
                for i, s in enumerate(STEPS):
                    yield Button(f"{float(s) * 100:.0f}%", id=f"size-{i}", classes="-tab")
        with Vertical(classes="card"):
            yield Static("Volume", classes="label")
            with Horizontal(id="volume"):
                yield Button("−", id="vol-down", classes="-tab")
                yield Static("", id="vol")
                yield Button("+", id="vol-up", classes="-tab")
                yield Button("mute", id="vol-mute", classes="-tab")
        yield Static("esc  close", id="foot", classes="dim")

    def on_mount(self) -> None:
        self.refresh_state()
        self.start_repainting()

    def refresh_state(self) -> None:
        try:
            _, scale, _ = monitor()
        except (OSError, ValueError, IndexError, KeyError, subprocess.SubprocessError):
            scale = 1.0
        for i, s in enumerate(STEPS):
            self.query_one(f"#size-{i}", Button).set_class(abs(float(s) - scale) < 0.01, "-on")
        try:
            self.query_one("#vol", Static).update(volume())
        except (OSError, subprocess.SubprocessError):
            self.query_one("#vol", Static).update("n/a")

    @on(Button.Pressed, "#sizes Button")
    def _size(self, event: Button.Pressed) -> None:
        idx = int(str(event.button.id).split("-")[1])
        self.apply_scale(STEPS[idx])

    @work(thread=True, exclusive=True, group="scale")
    def apply_scale(self, scale: str) -> None:
        try:
            name, _, mode = monitor()
            subprocess.run(["hyprctl", "keyword", "monitor", f"{name},{mode},auto,{scale}"],
                           capture_output=True, timeout=5)
            # The window rule placed us above the dock button in the OLD
            # logical size; at a bigger zoom that spot is now off the bottom
            # right of the screen, taking the panel you are using with it.
            # Same arithmetic as the panel-display rule in hyprland.conf.
            w, h = mode.split("@")[0].split("x")
            lw, lh = int(int(w) / float(scale)), int(int(h) / float(scale))
            subprocess.run(["hyprctl", "dispatch", "movewindowpixel",
                            f"exact {lw - 548} {lh - 356},class:^(th-panel-display)$"],
                           capture_output=True, timeout=5)
        except (OSError, ValueError, IndexError, KeyError, subprocess.SubprocessError):
            pass
        self.call_from_thread(self.refresh_state)

    @on(Button.Pressed, "#volume Button")
    def _volume(self, event: Button.Pressed) -> None:
        arg = {"vol-down": ["set-volume", "@DEFAULT_AUDIO_SINK@", "5%-"],
               "vol-up": ["set-volume", "@DEFAULT_AUDIO_SINK@", "5%+"],
               "vol-mute": ["set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"]}[str(event.button.id)]
        subprocess.run(["wpctl", *arg], capture_output=True, timeout=5)
        self.refresh_state()


if __name__ == "__main__":
    DisplayPanel().run()
