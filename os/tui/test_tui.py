#!/usr/bin/env python3
"""Self-check for the setup TUI.
Run: python3 tui/test_tui.py     (requires textual)

Drives the app the way a student would and asserts it reaches the right
answers. The disk assertions are the ones that matter: the drive they booted
from must not be reachable through the UI at all.

Note on driving Textual in tests: set Input.value directly and use
Button.press(). Synthesising clicks and keystrokes is fragile -- focus lands on
the button after a click, a Tab sent in the same burst as text is swallowed by
the Input, and a click positions the cursor mid-string so Backspace eats the
wrong character. All three cost real debugging time; none were app bugs.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

os.environ["TH_FAKE_DISKS"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "installer"))

from textual.widgets import Button, Input, RadioSet, Static  # noqa: E402

import install as app_mod  # noqa: E402


def press(app, sel="#next"):
    app.screen.query_one(sel, Button).press()


async def main() -> None:
    app = app_mod.Setup()
    async with app.run_test(size=(150, 44)) as pilot:
        await pilot.pause()

        # --- name: rejects rubbish, accepts a sane one ---
        app.screen.query_one("#name", Input).value = "bad name!"
        press(app)
        await pilot.pause()
        assert "server_name" not in app.cfg, "invalid name accepted"
        assert "!" in str(app.screen.query_one("#checks", Static)
                          .render()), "no validation warning shown"

        # typed with capitals, stored as the live check promised: lowercase.
        # It becomes the login name, and "Field-Node-1" versus "field-node-1"
        # is a wrong-password report waiting to happen.
        app.screen.query_one("#name", Input).value = "Field-Node-1"
        press(app)
        await pilot.pause()
        assert app.cfg["server_name"] == "field-node-1", app.cfg

        # --- there is nothing to quit to: both of Textual's quit keys are
        #     swallowed. On the live ISO the alternative was a root shell. ---
        await pilot.press("ctrl+c")
        await pilot.pause()
        await pilot.press("ctrl+q")
        await pilot.pause()
        assert app.is_running, "a quit key closed the installer"

        # --- enter in the first password box moves to the second, it does
        #     not submit the step with an empty confirmation ---
        pw = app.screen.query_one("#pw", Input)
        pw.focus()
        await pilot.press("h", "o", "r", "s", "e", "y", "enter")
        await pilot.pause()
        assert app.screen.focused is app.screen.query_one("#pw2", Input), (
            "enter did not move to the confirmation box")
        assert "password" not in app.cfg, "enter submitted a half-typed step"
        pw.value = ""

        # --- password: mismatch refused, match accepted ---
        app.screen.query_one("#pw", Input).value = "horizons123"
        app.screen.query_one("#pw2", Input).value = "different"
        press(app)
        await pilot.pause()
        assert "password" not in app.cfg, "mismatched passwords accepted"

        app.screen.query_one("#pw2", Input).value = "horizons123"
        press(app)
        await pilot.pause()
        assert app.cfg["password"] == "horizons123"

        # --- choice lists: arrows only move, space ticks, enter chooses
        #     and moves on. Enter used to do nothing here while the rail said
        #     "↵ next", because stock RadioSet just re-ticks the current row.
        rs = app.screen.query_one("#tz", app_mod.Choices)
        await pilot.press("down")
        await pilot.pause()
        assert rs.pressed_button.label.plain == "Australia/Melbourne", (
            "arrow key changed the choice, it should only move the highlight")
        await pilot.press("space")
        await pilot.pause()
        assert rs.pressed_button.label.plain == "Australia/Sydney", (
            "space did not tick the highlighted row")
        assert isinstance(app.screen, app_mod.RegionStep), "space advanced"

        # --- region: enter takes the ticked row through ---
        await pilot.press("enter")
        await pilot.pause()
        assert app.cfg["timezone"] == "Australia/Sydney", app.cfg

        # --- disks: the boot media must not even be listed ---
        rs = app.screen.query_one("#disk", RadioSet)
        labels = [b.label.plain for b in rs.children]
        assert len(labels) == 2, labels
        joined = " ".join(labels)
        assert "SanDisk" not in joined, "boot media offered in the UI"
        assert "256.0 GB" in joined and "500.0 GB" in joined, labels
        # type and current contents must be visible, or a student cannot tell
        # the Windows disk from the blank one
        assert "NVMe SSD" in joined and "now:" in joined, labels

        # pick the second disk
        rs.children[1].value = True
        await pilot.pause()
        press(app)
        await pilot.pause()
        assert app.cfg["disk"] == "/dev/sda", app.cfg

        # --- confirm screen states plainly what gets erased ---
        text = " ".join(str(s.render()) for s in app.screen.query(Static))
        # the disk is named the way the student picked it, not by device node
        assert "field-node-1" in text and "500.0 GB HDD" in text, text[:300]
        assert "/dev/sda" not in text, "device node shown to the student"
        assert "Erases" in text and "everything on that disk" in text

    # --- the auth frame: both screens wear it, lock is the testable one ---
    import lock as lock_mod

    app = lock_mod.Lock()
    async with app.run_test(size=(110, 30)) as pilot:
        await pilot.pause()
        rail = app.query_one("#rail-top-left", Static)
        assert "th │ locked" in str(rail.render()), rail.render()
        # the box must start below the banner, so an animation can run in the
        # field above it without ever being covered
        box = app.query_one("#authbox")
        assert box.region.y > app.query_one("#field").region.height * 0.9, (
            box.region, "auth box is overlapping the animated field")
        # a wrong password says so, with a coral mark and sage prose
        app.fail("that password is not right")
        await pilot.pause()
        err = app.query_one("#error", Static)
        assert err.display and "!" in str(err.render()), err.render()

    # Both auth screens carry Restart and Shut down. A Field Node sitting at
    # the sign-in screen is the one somebody most wants to turn off, and the
    # two screens are the same frame -- a student should not have to work out
    # which one they are looking at to find the power buttons.
    import greet as greet_mod
    for factory in (lock_mod.Lock, greet_mod.Greeter):
        app = factory()
        async with app.run_test(size=(92, 36)) as pilot:
            await pilot.pause()
            ids = [b.id for b in app.query(Button)]
            assert "restart" in ids and "shutdown" in ids, (factory.__name__, ids)
            box = app.query_one("#authbox")
            rail = app.query_one("#rail-bottom")
            assert box.region.y + box.region.height <= rail.region.y, (
                f"{factory.__name__} box clipped")

    # The wordmark settles rather than looping forever, and the settled frame
    # must actually show it. Freezing on a blank frame is the failure mode:
    # render_line used to restart the effect, re-scattering every glyph, and
    # nothing repainted after that.
    import banner as banner_mod

    # Ten cycles should be ten DIFFERENT effects, dealt from a shuffled deck
    # rather than picked at random -- random picking shows some three times and
    # others never. And every effect has to finish moving inside its cycle:
    # the repaint stops at _motion_ends, so an effect that staggers past it
    # (typewriter and fold both do) would freeze half-drawn.
    effects = banner_mod.Banner.EFFECTS
    assert len(effects) >= banner_mod.CYCLES, (len(effects), banner_mod.CYCLES)

    class _Deck(banner_mod.Banner):
        def __init__(self):
            self.cells = [banner_mod.Cell("X", y, x) for y in range(4) for x in range(40)]
            self.effect = ""
            self._w = self._h = 40
            self._cycles = 0
            self._deck = []
            self.started = 0.0
            self._held = False
            self._settled = False
            self._motion_ends = 0.0

    probe = _Deck()
    picks = []
    for _ in range(banner_mod.CYCLES):
        probe._begin()
        picks.append(probe.effect)
        assert probe._motion_ends <= banner_mod.TRAVEL + banner_mod.STAGGER + banner_mod.HOLD, (
            f"{probe.effect} still moving when its cycle ends")
    assert len(set(picks)) == banner_mod.CYCLES, f"repeats in ten cycles: {picks}"

    travel, stagger, hold, cycles = (banner_mod.TRAVEL, banner_mod.STAGGER,
                                     banner_mod.HOLD, banner_mod.CYCLES)
    banner_mod.TRAVEL, banner_mod.STAGGER = 0.05, 0.02
    banner_mod.HOLD, banner_mod.CYCLES = 0.05, 1
    try:
        app = lock_mod.Lock()
        async with app.run_test(size=(92, 36)) as pilot:
            await pilot.pause()
            widget = app.query_one(banner_mod.Banner)
            for _ in range(40):
                await pilot.pause(0.05)
                if widget._settled:
                    break
            assert widget._settled, "the wordmark never settled"
            ink = sum(1 for y in range(widget.size.height)
                      for seg in widget.render_line(y)._segments if seg.text.strip())
            assert ink > 20, f"settled frame is blank ({ink} glyphs)"
    finally:
        banner_mod.TRAVEL, banner_mod.STAGGER = travel, stagger
        banner_mod.HOLD, banner_mod.CYCLES = hold, cycles

    # the error line grows the box, which must never push it under the keybind
    # rail -- these run on whatever screen the donated laptop came with
    for rows in (24, 30, 36, 50):
        app = lock_mod.Lock()
        async with app.run_test(size=(92, rows)) as pilot:
            await pilot.pause()
            app.fail("that password is not right")
            await pilot.pause()
            box = app.query_one("#authbox")
            rail = app.query_one("#rail-bottom")
            assert box.region.y + box.region.height <= rail.region.y, (
                f"auth box clipped at {rows} rows")

    # --- every step must focus something, or its "↵" rail hint is a lie ---
    for step in (app_mod.NameStep, app_mod.PasswordStep, app_mod.RegionStep,
                 app_mod.DiskStep, app_mod.ConfirmStep):
        probe = app_mod.Setup()
        async with probe.run_test(size=(92, 36)) as pilot:
            await pilot.pause()
            probe.push_screen(step())
            await pilot.pause()
            assert probe.screen.focused is not None, f"{step.__name__} focuses nothing"

    # --- the restart button must never be a silent no-op: whatever it tried
    #     and whatever went wrong has to end up on screen ---
    tried = []

    class FakeResult:
        returncode = 1
        stderr = "nope"
        stdout = ""

    def fake_run(cmd, **kw):
        tried.append(cmd[0])
        return FakeResult()

    app_mod.subprocess.run = fake_run
    app_mod.time.sleep = lambda s: None
    app_mod.InstallStep.run_install = lambda self: None
    probe = app_mod.Setup()
    probe.cfg = {"disk": "/dev/sda", "server_name": "orion",
                 "password": "x", "timezone": "UTC"}
    async with probe.run_test(size=(92, 36)) as pilot:
        await pilot.pause()
        probe.push_screen(app_mod.InstallStep())
        await pilot.pause()
        # escape and ^B go "back" on every other step; here back would leave
        # install.sh running under a Confirm screen whose Yes starts another.
        await pilot.press("escape")
        await pilot.press("ctrl+b")
        await pilot.pause()
        assert isinstance(probe.screen, app_mod.InstallStep), (
            "back escaped the install screen")
        probe.screen.done()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        msg = str(probe.screen.query_one("#msg", Static).render())
        assert "restart failed" in msg, f"silent failure: {msg!r}"
        assert "reboot" in " ".join(tried), tried

    print("all TUI checks passed")


if __name__ == "__main__":
    asyncio.run(main())
