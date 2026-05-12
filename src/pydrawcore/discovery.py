from __future__ import annotations

from serial.tools.list_ports import comports

from .models import DiscoveredDevice


DRAWCORE_VID_PIDS = ("USB VID:PID=1A86:7523", "USB VID:PID=1A86:8040")


def discover_devices() -> list[DiscoveredDevice]:
    devices: list[DiscoveredDevice] = []
    for port in comports():
        hwid = getattr(port, "hwid", "") or ""
        if any(hwid.startswith(prefix) for prefix in DRAWCORE_VID_PIDS):
            devices.append(
                DiscoveredDevice(
                    port=str(port.device),
                    description=(getattr(port, "description", "") or ""),
                    hwid=hwid,
                )
            )
    return devices
