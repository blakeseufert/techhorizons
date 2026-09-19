#!/usr/bin/env python3
"""The network panel behind the dock's connection button.

Two tabs, because a Field Node is meant to be on the wire -- that is the whole
point of the cable the student crimps in Stage 0 -- but somebody trying the OS
out on a laptop at home has only Wi-Fi, and telling them "plug in" is not an
answer.

Read-only except for joining a Wi-Fi network. DNS is shown but not editable:
resolver settings are a good way to make a machine look broken in a way no
fourteen-year-old will connect to something they changed a week ago.
"""
from __future__ import annotations

import sys
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "tui"))

import netinfo  # noqa: E402
from chrome import Repainting  # noqa: E402

REFRESH = 2.0


def kv_row(left_key: str, left_val: str, right_key: str, right_val: str,
           left_warn: bool = False, right_warn: bool = False) -> str:
    """One line of the two-column readout, dim keys and sage values."""
    def val(text: str, warn: bool) -> str:
        return f"[#FF6846]{text}[/]" if warn else f"[#DBE4C6]{text}[/]"
    return (f"[#DBE4C6 45%]{left_key:<14}[/]{val(left_val, left_warn):<12}"
            f"   [#DBE4C6 45%]{right_key:<14}[/]{val(right_val, right_warn)}")


class NetworkPanel(Repainting, App):
    CSS_PATH = "panel.tcss"
    TITLE = "Network"

    BINDINGS = [("escape", "quit", "close"), ("q", "quit", "close")]

    def __init__(self) -> None:
        super().__init__()
        self.tab = "wired"
        self.rates: netinfo.Rates | None = None
        self.iface = ""
        self.ping_text = "…"
        self.loss_text = "…"
        self.networks: list[dict[str, str]] = []
        self.pending_ssid = ""

    def compose(self) -> ComposeResult:
        with Horizontal(id="tabs"):
            yield Button("Ethernet", id="tab-wired", classes="-tab")
            yield Button("Wi-Fi", id="tab-wireless", classes="-tab")
        yield Static("", id="head")
        yield Static("", id="body")
        with Vertical(id="join"):
            yield Static("", id="join-label", classes="dim")
            yield Input(password=True, placeholder="password", id="join-pw")
        yield Static("esc  close", id="foot", classes="dim")

    def on_mount(self) -> None:
        self.query_one("#join", Vertical).display = False
        self.select_tab("wired")
        self.set_interval(REFRESH, self.refresh_view)
        self.start_repainting()
        self.probe_ping()

    # ---- tabs ---------------------------------------------------------
    @on(Button.Pressed, ".-tab")
    def _tab(self, event: Button.Pressed) -> None:
        self.select_tab("wired" if event.button.id == "tab-wired" else "wireless")

    def select_tab(self, tab: str) -> None:
        self.tab = tab
        for name in ("wired", "wireless"):
            self.query_one(f"#tab-{name}", Button).set_class(name == tab, "-on")
        ifaces = netinfo.interfaces()
        names = ifaces["wired"] if tab == "wired" else ifaces["wireless"]
        self.iface = names[0] if names else ""
        self.rates = netinfo.Rates(self.iface) if self.iface else None
        self.query_one("#join", Vertical).display = False
        if tab == "wireless":
            self.scan()
        self.refresh_view()
        self.probe_ping()

    # ---- readout ------------------------------------------------------
    def refresh_view(self) -> None:
        if self.tab == "wired":
            self.render_wired()
        else:
            self.render_wireless()

    def render_wired(self) -> None:
        head = self.query_one("#head", Static)
        body = self.query_one("#body", Static)
        if not self.iface:
            head.update("[#DBE4C6]Ethernet[/]\n[#FF6846]NO WIRED INTERFACE[/]")
            body.update("[#DBE4C6 45%]No wired port on this machine. "
                        "Use the Wi-Fi tab.[/]")
            return

        up = netinfo.carrier(self.iface)
        state = "HANDLING PACKETS" if up else "CABLE UNPLUGGED"
        colour = "#DBE4C6 45%" if up else "#FF6846"
        head.update(f"[#DBE4C6]Ethernet[/]  [#DBE4C6 45%]{self.iface}[/]\n"
                    f"[{colour}]{state}[/]")

        rx_rate, tx_rate = self.rates.sample() if self.rates else (0.0, 0.0)
        rx_total, tx_total = netinfo.counters(self.iface)
        addr = netinfo.addresses(self.iface)
        lines = [
            kv_row("Ping", self.ping_text, "Packet Loss", self.loss_text,
                   left_warn=self.ping_text == "Timeout",
                   right_warn=self.loss_text not in ("0%", "…")),
            kv_row("Receiving", netinfo.human_bytes(rx_rate, rate=True),
                   "Sending", netinfo.human_bytes(tx_rate, rate=True)),
            kv_row("Downloaded", netinfo.human_bytes(rx_total),
                   "Uploaded", netinfo.human_bytes(tx_total)),
            kv_row("IP Address", addr["ip"] or "none",
                   "Gateway", addr["gateway"] or "none",
                   left_warn=not addr["ip"]),
            "",
            "[#DBE4C6 45%]DNS[/]           [#DBE4C6]"
            + (", ".join(netinfo.dns_servers()) or "none") + "[/]",
        ]
        body.update("\n".join(lines))

    def render_wireless(self) -> None:
        head = self.query_one("#head", Static)
        body = self.query_one("#body", Static)
        if not self.iface:
            head.update("[#DBE4C6]Wi-Fi[/]\n[#FF6846]NO WIRELESS ADAPTER[/]")
            body.update("[#DBE4C6 45%]This machine has no Wi-Fi. "
                        "Plug in a cable.[/]")
            return

        connected = any(n.get("active") for n in self.networks)
        head.update(f"[#DBE4C6]Wi-Fi[/]  [#DBE4C6 45%]{self.iface}[/]\n"
                    f"[#DBE4C6 45%]{'CONNECTED' if connected else 'SCANNING'}[/]")

        if not self.networks:
            body.update("[#DBE4C6 45%]Looking for networks…[/]")
            return

        lines = []
        for i, net in enumerate(self.networks[:8]):
            mark = "[#FF6846]●[/]" if net.get("active") else "[#DBE4C6 22%]●[/]"
            lock = "" if net["security"] in ("", "open", "--") else " 🔒"
            # The whole row is a link: a twelve-year-old clicks the network
            # they want, the number is for whoever prefers the keyboard.
            lines.append(f"[@click=app.pick({i})]{mark} [#DBE4C6 45%]{i + 1}[/]  "
                         f"[#DBE4C6]{net['ssid'][:24]:<24}[/]"
                         f"[#DBE4C6 45%]{net['signal']:>3}%{lock}[/][/]")
        lines.append("")
        lines.append("[#DBE4C6 45%]click a network to join it[/]")
        body.update("\n".join(lines))

    # ---- work ---------------------------------------------------------
    @work(thread=True, exclusive=True, group="ping")
    def probe_ping(self) -> None:
        target = netinfo.addresses(self.iface)["gateway"] if self.iface else ""
        result = netinfo.ping(target)
        self.call_from_thread(self.set_ping, *result)

    def set_ping(self, latency: str, loss: str) -> None:
        self.ping_text, self.loss_text = latency, loss
        self.refresh_view()

    @work(thread=True, exclusive=True, group="scan")
    def scan(self) -> None:
        found = netinfo.wifi_networks()
        self.call_from_thread(self.set_networks, found)

    def set_networks(self, found: list[dict[str, str]]) -> None:
        self.networks = found
        self.refresh_view()

    # ---- joining ------------------------------------------------------
    def on_key(self, event) -> None:
        if self.tab != "wireless" or self.query_one("#join", Vertical).display:
            return
        if event.key.isdigit() and event.key != "0":
            idx = int(event.key) - 1
            if idx < len(self.networks):
                self.begin_join(self.networks[idx])

    def action_pick(self, idx: int) -> None:
        if self.tab == "wireless" and idx < len(self.networks):
            self.begin_join(self.networks[idx])

    def begin_join(self, net: dict[str, str]) -> None:
        self.pending_ssid = net["ssid"]
        box = self.query_one("#join", Vertical)
        self.query_one("#join-label", Static).update(f"password for {net['ssid']}")
        box.display = True
        field = self.query_one("#join-pw", Input)
        field.value = ""
        if net["security"] in ("", "open", "--"):
            self.join("")
        else:
            field.focus()

    @on(Input.Submitted, "#join-pw")
    def _submit(self) -> None:
        field = self.query_one("#join-pw", Input)
        password = field.value
        field.value = ""
        self.join(password)

    def join(self, password: str) -> None:
        self.query_one("#join-label", Static).update(
            f"joining {self.pending_ssid}…")
        self.connect(self.pending_ssid, password)

    @work(thread=True, exclusive=True, group="join")
    def connect(self, ssid: str, password: str) -> None:
        ok, message = netinfo.wifi_connect(ssid, password)
        self.call_from_thread(self.joined, ok, message)

    def joined(self, ok: bool, message: str) -> None:
        if ok:
            self.query_one("#join", Vertical).display = False
            self.select_tab("wireless")
            return
        self.query_one("#join-label", Static).update(
            f"[#FF6846]! [/][#DBE4C6]{message[:52]}[/]")


if __name__ == "__main__":
    NetworkPanel().run()
