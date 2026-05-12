from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class DiscoveredDevice:
    port: str
    description: str
    hwid: str


@dataclass(slots=True, frozen=True)
class DeviceInfo:
    port: str | None
    firmware: str
    nickname: str | None = None
    input_voltage_ok: bool | None = None
    status: str | None = None


@dataclass(slots=True)
class MotionConfig:
    feed_rate_xy: int = 1200
    feed_rate_pen_up: int = 1200
    feed_rate_pen_down: int = 600
    pen_up_position: int = 60
    pen_down_position: int = 30
