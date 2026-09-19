"""Reading the network state off the machine.

Kept apart from the panel that draws it so it can be exercised without a
terminal -- see the self-check at the bottom.
"""
from __future__ import annotations

import os
import re
import subprocess
import time

SYS = "/sys/class/net"


def _run(cmd: list[str], timeout: float = 4.0) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout


def interfaces() -> dict[str, list[str]]:
    """Wired and wireless interface names, loopback and virtual ones dropped."""
    wired: list[str] = []
    wireless: list[str] = []
    try:
        names = sorted(os.listdir(SYS))
    except OSError:
        return {"wired": [], "wireless": []}
    for name in names:
        if name == "lo" or name.startswith(("veth", "docker", "br-", "virbr")):
            continue
        if os.path.isdir(os.path.join(SYS, name, "wireless")) or name.startswith("wl"):
            wireless.append(name)
        else:
            wired.append(name)
    return {"wired": wired, "wireless": wireless}


def _read(path: str) -> str:
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return ""


def carrier(iface: str) -> bool:
    """Is a cable actually plugged in / is the radio associated."""
    return _read(os.path.join(SYS, iface, "carrier")) == "1"


def counters(iface: str) -> tuple[int, int]:
    base = os.path.join(SYS, iface, "statistics")
    def num(name: str) -> int:
        raw = _read(os.path.join(base, name))
        return int(raw) if raw.isdigit() else 0
    return num("rx_bytes"), num("tx_bytes")


def parse_addr(text: str) -> str:
    """The IPv4 address out of `ip addr show` output."""
    match = re.search(r"\binet (\d+\.\d+\.\d+\.\d+/\d+)", text)
    return match.group(1) if match else ""


def parse_gateway(text: str, iface: str) -> str:
    """The default gateway for one interface out of `ip route` output."""
    for line in text.splitlines():
        if line.startswith("default via") and f" dev {iface}" in line:
            parts = line.split()
            if len(parts) >= 3:
                return parts[2]
    return ""


def addresses(iface: str) -> dict[str, str]:
    """IPv4 address and default gateway for this interface.

    Parsed out of the text output, not `ip -j`: Alpine ships busybox ip, which
    has no JSON mode at all -- asking for it just prints the usage message, and
    the panel quietly reported "none" on a machine that was plainly online.
    """
    return {
        "ip": parse_addr(_run(["ip", "-4", "addr", "show", "dev", iface])),
        "gateway": parse_gateway(_run(["ip", "route", "show", "default"]), iface),
    }


def dns_servers() -> list[str]:
    servers = []
    for line in _read("/etc/resolv.conf").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "nameserver":
            servers.append(parts[1])
    return servers


def ping(target: str) -> tuple[str, str]:
    """(latency, loss) as display strings. Empty target reads as a timeout."""
    if not target:
        return "Timeout", "100%"
    out = _run(["ping", "-c", "3", "-W", "1", target], timeout=8)
    loss = "100%"
    match = re.search(r"(\d+(?:\.\d+)?)% packet loss", out)
    if match:
        loss = f"{float(match.group(1)):.0f}%"
    match = re.search(r"min/avg/max[^=]*= ([\d.]+)/([\d.]+)/", out)
    if match:
        return f"{float(match.group(2)):.0f} ms", loss
    return "Timeout", loss


def human_bytes(n: float, rate: bool = False) -> str:
    unit = "B/s" if rate else "B"
    for step, suffix in ((1024 ** 3, "GB"), (1024 ** 2, "MB"), (1024, "KB")):
        if n >= step:
            return f"{n / step:.1f} {suffix}{'/s' if rate else ''}"
    return f"{n:.0f} {unit}"


class Rates:
    """Byte counters sampled between calls, turned into a per-second rate."""

    def __init__(self, iface: str) -> None:
        self.iface = iface
        self.rx, self.tx = counters(iface)
        self.at = time.monotonic()

    def sample(self) -> tuple[float, float]:
        rx, tx = counters(self.iface)
        now = time.monotonic()
        gap = max(now - self.at, 0.001)
        rates = ((rx - self.rx) / gap, (tx - self.tx) / gap)
        self.rx, self.tx, self.at = rx, tx, now
        # A counter that went backwards means the interface reset; report zero
        # rather than a nonsense negative rate.
        return max(rates[0], 0.0), max(rates[1], 0.0)


def wifi_networks() -> list[dict[str, str]]:
    """Visible SSIDs, strongest first, duplicates collapsed."""
    raw = _run(["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list"], timeout=10)
    seen: dict[str, dict[str, str]] = {}
    for line in raw.splitlines():
        # nmcli escapes colons inside fields as "\:" -- split on the real ones
        parts = re.split(r"(?<!\\):", line)
        if len(parts) < 4:
            continue
        in_use, ssid, signal, security = parts[0], parts[1].replace("\\:", ":"), parts[2], parts[3]
        if not ssid:
            continue
        entry = {
            "ssid": ssid,
            "signal": signal or "0",
            "security": security or "open",
            "active": in_use.strip() == "*",
        }
        best = seen.get(ssid)
        if best is None or int(entry["signal"]) > int(best["signal"]):
            seen[ssid] = entry
    return sorted(seen.values(), key=lambda e: int(e["signal"]), reverse=True)


def wifi_connect(ssid: str, password: str) -> tuple[bool, str]:
    cmd = ["nmcli", "dev", "wifi", "connect", ssid]
    if password:
        cmd += ["password", password]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if out.returncode == 0:
        return True, "connected"
    message = (out.stderr or out.stdout).strip().splitlines()
    return False, (message[-1] if message else "could not connect")


if __name__ == "__main__":
    assert human_bytes(0) == "0 B"
    assert human_bytes(867) == "867 B"
    assert human_bytes(124.4 * 1024, rate=True) == "124.4 KB/s"
    assert human_bytes(123.3 * 1024 ** 2) == "123.3 MB"
    # Real busybox output from a field node -- the format that broke the
    # JSON-based version.
    ADDR = """2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc pfifo_fast state UP qlen 1000
    inet 192.0.2.168/24 brd 192.0.2.255 scope global dynamic noprefixroute eth0
       valid_lft 80100sec preferred_lft 80100sec"""
    ROUTE = """default via 192.0.2.1 dev eth0  src 192.0.2.168  metric 100
192.0.2.0/24 dev eth0 scope link  src 192.0.2.168  metric 100"""
    assert parse_addr(ADDR) == "192.0.2.168/24", parse_addr(ADDR)
    assert parse_gateway(ROUTE, "eth0") == "192.0.2.1", parse_gateway(ROUTE, "eth0")
    assert parse_gateway(ROUTE, "wlan0") == ""
    assert parse_addr("no address here") == ""

    ifaces = interfaces()
    assert "lo" not in ifaces["wired"] and "lo" not in ifaces["wireless"]
    print("netinfo self-check passed;", ifaces)
