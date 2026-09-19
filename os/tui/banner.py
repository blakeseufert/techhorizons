"""Animated Tech Horizons banner, shared by the login and lock screens.

Glyphs fly in from anywhere on the widget and converge into the wordmark, then
rest before the next effect. Same idea as terminaltexteffects, which Omarchy's
screensaver shells out to -- reimplemented here because tte is not packaged for
Alpine and this has to work with no network and no pip.
"""
from __future__ import annotations

import math
import random
import time
from pathlib import Path

from rich.segment import Segment
from rich.style import Style
from textual.strip import Strip
from textual.widget import Widget

ART_FILE = Path("/opt/techhorizons/greeter/banner.txt")
FALLBACK = r"""
 _____         _       _   _            _
|_   _|__  ___| |__   | | | | ___  _ __(_)_______  _ __  ___
  | |/ _ \/ __| '_ \  | |_| |/ _ \| '__| |_  / _ \| '_ \/ __|
  | |  __/ (__| | | | |  _  | (_) | |  | |/ / (_) | | | \__ \
  |_|\___|\___|_| |_| |_| |_|\___/|_|  |_/___\___/|_| |_|___/
"""

GLYPHS = "01#%&$@*+=-_/\\|<>[]{}"
TRAVEL = 1.9      # seconds for a glyph to reach home
STAGGER = 0.9     # spread of per-glyph start times
HOLD = 4.5        # rest before the next effect

# How many times the wordmark flies in before it simply stays put.
#
# It used to loop forever, which is what a screensaver does -- and on a machine
# with no GPU acceleration a permanent animation is a permanent tax. Hyprland
# sat at 18% of a core for a sign-in screen nobody was looking at, which on a
# donated laptop is battery burning in a bag. Two passes reads as "this thing
# is alive", and then it stops: settled, 0%.
#
# Set to 0 for the old endless loop.
CYCLES = 10

# The background must be painted by us: overriding render_line means Textual
# does not fill the widget background, so a blank Strip leaves the terminal's
# own colour showing and the banner half of the screen ends up a different
# shade from the card half.
# Design system, section 07: ink-deep ground, sage content, coral only on what
# is moving -- the same three signals the rest of the terminal UI uses. The old
# navy and indigo here predate that and made the login screen look like a
# different operating system from the installer that had just run.
BG = "#141615"
BLANK = Style(bgcolor=BG)
SETTLED = Style(color="#DBE4C6", bgcolor=BG)
MOVING = Style(color="#FF6846", bgcolor=BG, bold=True)
# Not yet lit -- the spotlight effect shows the whole wordmark faintly and
# brings it up as the light passes.
DIM = Style(color="#4A4F45", bgcolor=BG)
EMBERS = "▓▒░"


def _lerp_hex(a: str, b: str, t: float) -> str:
    ra, ga, ba = int(a[1:3], 16), int(a[3:5], 16), int(a[5:7], 16)
    rb, gb, bb = int(b[1:3], 16), int(b[3:5], 16), int(b[5:7], 16)
    return "#%02X%02X%02X" % (round(ra + (rb - ra) * t), round(ga + (gb - ga) * t),
                              round(ba + (bb - ba) * t))


# A glyph in flight cools from coral to sage as it nears home, rather than
# snapping between two colours. Eight steps is plenty on a terminal and keeps
# the Style objects shared rather than made per cell per frame.
GRADIENT = [Style(color=_lerp_hex("#FF6846", "#DBE4C6", i / 7), bgcolor=BG, bold=(i < 4))
            for i in range(8)]


def _ease_in(p: float) -> float:
    return p * p * p


def _load_art() -> list[str]:
    try:
        lines = ART_FILE.read_text().rstrip("\n").split("\n")
        if any(l.strip() for l in lines):
            return lines
    except OSError:
        pass
    return FALLBACK.strip("\n").split("\n")


def _ease_out(p: float) -> float:
    return 1.0 - (1.0 - p) ** 3


class Cell:
    __slots__ = ("ch", "hy", "hx", "delay", "dur", "path", "scramble", "glyphs")

    def __init__(self, ch: str, hy: int, hx: int):
        self.ch, self.hy, self.hx = ch, hy, hx
        self.delay = 0.0           # seconds after the effect starts
        self.dur = TRAVEL          # seconds in flight once started
        self.path: list[tuple[float, float]] = []   # waypoints, home last
        self.scramble = 0.0        # tumble in place until this monotonic time
        self.glyphs = GLYPHS       # what to tumble with


def _along(path: list[tuple[float, float]], e: float) -> tuple[int, int]:
    """Position along a polyline at eased progress e in [0, 1]."""
    segs = len(path) - 1
    if segs < 1:
        return int(round(path[0][0])), int(round(path[0][1]))
    s = min(e, 1.0) * segs
    i = min(int(s), segs - 1)
    t = s - i
    (y0, x0), (y1, x1) = path[i], path[i + 1]
    return int(round(y0 + (y1 - y0) * t)), int(round(x0 + (x1 - x0) * t))


class Banner(Widget):
    """Renders the animated wordmark. Height is set by the caller's CSS."""

    # Twenty effects, ten shown per boot, dealt from a shuffled deck -- so two
    # boots in a row look different. Modelled on terminaltexteffects' catalogue
    # (fireworks, blackhole, rain, matrix, beams, burn, waves, spotlights,
    # slide, expand...) but each is a few lines here: a glyph gets a path of
    # waypoints and a delay, or a deadline to stop tumbling in place. The
    # first ten were all one primitive -- a straight glide in coral -- which
    # is why they read as variations of the same thing.
    EFFECTS = ("scatter", "converge", "rise", "drop", "spiral", "fold", "expand",
               "fireworks", "blackhole", "rain", "matrix", "slide", "waves",
               "beam", "burn", "decrypt", "wipe", "typewriter", "breathe",
               "spotlight")
    # glyphs travel along their path; everything else appears in place
    PATH_EFFECTS = {"scatter", "converge", "rise", "drop", "spiral", "fold", "expand",
                    "fireworks", "blackhole", "rain", "matrix", "slide"}
    GRAVITY = {"rain", "matrix"}        # ease in: falling, not gliding
    TUMBLING = {"matrix"}               # random glyph while in flight
    SPOT = 1.8                          # spotlight roams for SPOT * TRAVEL
    MOVING_EFFECTS = PATH_EFFECTS       # kept for callers that ask

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.art = _load_art()
        self.cells: list[Cell] = []
        self.effect = ""
        self.started = 0.0
        self._w = self._h = 0
        self._held = False
        self._cycles = 0
        self._settled = False
        self._deck: list[str] = []
        # When the current effect actually stops moving. Not a constant:
        # typewriter and fold stagger their glyphs well past TRAVEL + STAGGER,
        # and using that as the cutoff froze them mid-animation.
        self._motion_ends = 0.0

    def on_mount(self) -> None:
        # Tick often, but only REPAINT while something is actually moving.
        #
        # This used to refresh unconditionally at 20fps, including through the
        # 4.5s hold at the end of every effect when the frame is identical --
        # about two thirds of the cycle spent redrawing the same picture. Each
        # of those repaints walks the widget, redraws the terminal and makes
        # the compositor recomposite the screen, which on a machine with no GPU
        # acceleration is the single most expensive thing happening. Hyprland
        # sat at 70% CPU on the lock screen; the Python was 2% of it.
        self.set_interval(1 / 15, self._tick)

    def _tick(self) -> None:
        """Drive the cycle. The ONLY place that starts or ends an effect.

        This used to share the job with render_line, which restarted the effect
        on its own timer -- so the cycle counter ran away and the wordmark
        never settled, because the two disagreed about when a cycle had ended.
        """
        if self._settled:
            return

        if not self.effect:            # first frame of the session
            self._begin()
            self.refresh()
            return

        elapsed = time.monotonic() - self.started
        if elapsed <= self._motion_ends:
            self._held = False
            self.refresh()
            return

        # Arrived. Paint the resting frame once, then hold without touching
        # the screen until it is time for the next effect.
        if not self._held:
            self._held = True
            self.refresh()
            return

        if elapsed <= self._motion_ends + HOLD:
            return

        if CYCLES and self._cycles >= CYCLES:
            self._settled = True
            self.refresh()
            return

        self._begin()
        self._held = False
        self.refresh()

    def _layout(self, w: int, h: int) -> None:
        self._w, self._h = w, h
        art_h = len(self.art)
        art_w = max((len(l) for l in self.art), default=0)
        top = max(0, (h - art_h) // 2)
        left = max(0, (w - art_w) // 2)
        self.cells = [
            Cell(ch, top + y, left + x)
            for y, line in enumerate(self.art)
            for x, ch in enumerate(line)
            if ch != " " and top + y < h and left + x < w
        ]
        self._begin()

    def _begin(self) -> None:
        self._cycles += 1

        # Deal from a shuffled deck rather than picking at random each time.
        # Random picking repeats: over ten cycles of six effects you would see
        # some three times and others never. A deck shows every effect once
        # before any comes round again, and is reshuffled so the order differs
        # each boot. The one guard is against the same effect landing back to
        # back across a reshuffle.
        if not self._deck:
            self._deck = list(self.EFFECTS)
            random.shuffle(self._deck)
            if len(self._deck) > 1 and self._deck[-1] == self.effect:
                self._deck[0], self._deck[-1] = self._deck[-1], self._deck[0]
        self.effect = self._deck.pop()
        self.started = time.monotonic()
        w, h = self._w, self._h
        maxx = max((c.hx for c in self.cells), default=1)
        minx = min((c.hx for c in self.cells), default=0)
        miny = min((c.hy for c in self.cells), default=0)
        maxy = max((c.hy for c in self.cells), default=0)
        cy0, cx0 = h / 2, w / 2
        n = max(1, len(self.cells))
        U = random.uniform
        fx = self.effect
        # fireworks: three launch sites along the bottom, fired in turn
        sites = [U(w * 0.15, w * 0.85) for _ in range(3)]

        for i, c in enumerate(self.cells):
            c.scramble = 0.0
            c.path = []
            c.dur = TRAVEL
            c.glyphs = GLYPHS
            c.delay = U(0.0, STAGGER)
            home = (float(c.hy), float(c.hx))
            if fx == "scatter":
                c.path = [(U(0, h - 1), U(0, w - 1)), home]
            elif fx == "converge":
                edge = random.randrange(4)
                start = [(0, U(0, w - 1)), (h - 1, U(0, w - 1)),
                         (U(0, h - 1), 0), (U(0, h - 1), w - 1)][edge]
                c.path = [start, home]
            elif fx == "rise":
                c.path = [(h - 1, c.hx), home]
                c.delay = (c.hy - miny) * TRAVEL * 0.116 + U(0.0, TRAVEL * 0.08)
            elif fx == "drop":
                c.path = [(0, c.hx), home]
                c.delay = U(0.0, STAGGER) + (c.hx % 7) * TRAVEL * 0.026
            elif fx == "spiral":
                # Off a ring around the middle, so everything sweeps inward.
                angle = (c.hx + c.hy) * 0.5
                radius = max(w, h) * 0.6
                c.path = [(max(0, min(h - 1, cy0 + math.sin(angle) * radius)),
                           max(0, min(w - 1, cx0 + math.cos(angle) * radius))), home]
            elif fx == "fold":
                # Both halves fly in from the outside edges to meet.
                c.path = [(c.hy, 0 if c.hx < maxx / 2 else w - 1), home]
                c.delay = abs(c.hx - maxx / 2) / max(maxx, 1) * TRAVEL * 0.7
            elif fx == "expand":
                # Everything bursts out of one point in the middle.
                c.path = [(cy0, cx0), home]
                c.delay = U(0.0, TRAVEL * 0.21)
            elif fx == "fireworks":
                # Up from a launch site, burst, then drift to home. Three
                # shells, one after another, so the wordmark assembles in
                # thirds.
                shell = i * 3 // n
                lx = sites[shell]
                burst = (U(0, max(0, cy0 - 1)), lx + U(-w * 0.12, w * 0.12))
                c.path = [(h - 1, lx), burst, home]
                c.delay = shell * TRAVEL * 0.37 + U(0.0, TRAVEL * 0.06)
                c.dur = TRAVEL * 1.26
            elif fx == "blackhole":
                # Everything is pulled onto a ring, swings a quarter turn
                # around it, then is flung to where it belongs.
                th = i / n * math.tau
                ry, rx = h * 0.32, w * 0.28
                ring1 = (cy0 + math.sin(th) * ry, cx0 + math.cos(th) * rx)
                ring2 = (cy0 + math.sin(th + 1.6) * ry, cx0 + math.cos(th + 1.6) * rx)
                c.path = [(U(0, h - 1), U(0, w - 1)), ring1, ring2, home]
                c.delay = U(0.0, TRAVEL * 0.16)
                c.dur = TRAVEL * 1.58
            elif fx == "rain":
                # Falls in from above the top edge, each drop on its own time.
                # Start just above the edge: the fall is the effect, and a
                # drop that starts a screen higher spends its time invisible.
                c.path = [(-1 - U(0, 2), c.hx), home]
                c.delay = U(0.0, TRAVEL * 0.74)
                c.dur = TRAVEL * 0.63
            elif fx == "matrix":
                # Columns of tumbling glyphs pour down and resolve where they
                # land.
                c.path = [(-1, c.hx), home]
                c.delay = (c.hx % 9) * TRAVEL * 0.063 + U(0.0, TRAVEL * 0.32)
                c.dur = TRAVEL * 0.74
            elif fx == "slide":
                # Rows slide in from alternate sides, top to bottom.
                from_left = (c.hy - miny) % 2 == 0
                c.path = [(c.hy, -2 if from_left else w + 1), home]
                c.delay = (c.hy - miny) * TRAVEL * 0.095 + U(0.0, TRAVEL * 0.05)
                c.dur = TRAVEL * 0.74
            elif fx == "waves":
                # A swell runs left to right and each glyph bobs on it,
                # settling as the wave dies out.
                c.delay = (c.hx - minx) * TRAVEL * 0.008
                c.dur = TRAVEL * 0.84
            elif fx == "beam":
                # A vertical beam sweeps across; glyphs flare as it passes.
                c.delay = (c.hx - minx) * TRAVEL * 0.0095
                c.scramble = self.started + c.delay + TRAVEL * 0.13
            elif fx == "burn":
                # Lit from the bottom row up, embers first, then the glyph.
                c.delay = (maxy - c.hy) * TRAVEL * 0.18 + U(0.0, TRAVEL * 0.13)
                c.scramble = self.started + c.delay + TRAVEL * 0.24
                c.glyphs = EMBERS
            elif fx == "decrypt":
                c.scramble = self.started + c.delay + U(TRAVEL * 0.16, TRAVEL * 0.58)
            elif fx == "wipe":
                c.delay = (c.hx / max(maxx, 1)) * TRAVEL * 0.8
            elif fx == "typewriter":
                # Struck one column at a time, left to right, with the glyph
                # tumbling until its moment arrives.
                c.delay = (c.hx / max(maxx, 1)) * TRAVEL * 1.6
                c.scramble = self.started + c.delay
            elif fx == "spotlight":
                c.delay = 0.0
            # "breathe": each glyph simply fades up on its own stagger

        # The last glyph to arrive decides when this effect is done: its own
        # delay plus its flight, or its scramble deadline for the effects that
        # tumble in place.
        latest = 0.0
        for c in self.cells:
            # in-place glyphs flare coral for the first 28% of dur (see
            # render_line), so that is when they are actually at rest
            arrive = c.delay + (c.dur if (fx in self.PATH_EFFECTS or fx == "waves") else 0.28 * c.dur)
            if c.scramble:
                arrive = max(arrive, c.scramble - self.started)
            latest = max(latest, arrive)
        if fx == "spotlight":
            latest = self.SPOT * TRAVEL
        self._motion_ends = latest + TRAVEL * 0.08

    def render_line(self, y: int) -> Strip:
        w = self.size.width
        h = self.size.height
        if not w or not h:
            return Strip([Segment(" " * max(w, 0), BLANK)], max(w, 0))
        if (w, h) != (self._w, self._h) or not self.cells:
            self._layout(w, h)
        # Once settled, never restart the effect: _begin() re-scatters every
        # glyph to a random start position, and since nothing repaints after
        # this point the wordmark would freeze on that first blank frame --
        # which is exactly what happened. Draw it at rest instead.
        if self._settled:
            row: dict[int, tuple[str, Style]] = {}
            for c in self.cells:
                if c.hy == y:
                    row[c.hx] = (c.ch, SETTLED)
            return self._strip(row, w)

        now = time.monotonic()
        elapsed = now - self.started
        fx = self.effect
        on_path = fx in self.PATH_EFFECTS

        if fx == "spotlight":
            # The whole wordmark is there from the first frame, unlit. A
            # light roams over it, then everything comes up together.
            lit_all = elapsed >= self.SPOT * TRAVEL
            t = elapsed * 1.7
            sy = self._h / 2 + math.sin(t * 1.3) * self._h * 0.3
            sx = self._w / 2 + math.cos(t) * self._w * 0.36
            row: dict[int, tuple[str, Style]] = {}
            for c in self.cells:
                if c.hy != y:
                    continue
                if lit_all:
                    style = SETTLED
                elif ((c.hx - sx) / 7) ** 2 + ((c.hy - sy) / 2.2) ** 2 <= 1.0:
                    style = MOVING
                else:
                    style = DIM
                row[c.hx] = (c.ch, style)
            return self._strip(row, w)

        row = {}
        for c in self.cells:
            t = elapsed - c.delay
            if t < 0:
                continue
            p = min(1.0, t / c.dur)
            ch, style = c.ch, SETTLED
            if on_path:
                e = _ease_in(p) if fx in self.GRAVITY else _ease_out(p)
                cy, cx = _along(c.path, e) if p < 1.0 else (c.hy, c.hx)
                if p < 1.0:
                    style = GRADIENT[int(p * 7)]
                    if fx in self.TUMBLING:
                        ch = random.choice(GLYPHS)
            elif fx == "waves":
                cx = c.hx
                if p < 1.0:
                    amp = 2.0 * (1.0 - p)
                    cy = c.hy + int(round(amp * math.sin(math.tau * (c.hx / 12 - p * 2.0))))
                    style = GRADIENT[int(p * 7)]
                else:
                    cy = c.hy
            else:
                cy, cx = c.hy, c.hx
                if c.scramble and now < c.scramble:
                    ch, style = random.choice(c.glyphs), MOVING
                elif p < 0.28:
                    style = MOVING
            if cy == y and 0 <= cx < w:
                row[cx] = (ch, style)

        return self._strip(row, w)

    def _strip(self, row: dict[int, tuple[str, Style]], w: int) -> Strip:
        """One rendered line: glyphs at their columns, our background between.

        The background has to be painted by us -- overriding render_line means
        Textual will not do it, and a bare Strip leaves the terminal's own
        colour showing through.
        """
        if not row:
            return Strip([Segment(" " * w, BLANK)], w)
        segments, x = [], 0
        for cx in sorted(row):
            if cx > x:
                segments.append(Segment(" " * (cx - x), BLANK))
            ch, style = row[cx]
            segments.append(Segment(ch, style))
            x = cx + 1
        if x < w:
            segments.append(Segment(" " * (w - x), BLANK))
        return Strip(segments, w)
