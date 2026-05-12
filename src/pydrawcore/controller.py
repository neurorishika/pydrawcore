from __future__ import annotations

from .discovery import discover_devices
from .exceptions import ConnectionError
from .models import DeviceInfo, MotionConfig
from .transport import BaseTransport, open_transport


class DrawCoreController:
    def __init__(self, transport: BaseTransport, motion: MotionConfig | None = None):
        self._transport = transport
        self.motion = motion or MotionConfig()

    @classmethod
    def connect(
        cls,
        port: str,
        *,
        timeout: float = 1.0,
        motion: MotionConfig | None = None,
    ) -> "DrawCoreController":
        return cls(open_transport(port=port, timeout=timeout), motion=motion)

    @classmethod
    def auto_connect(
        cls,
        *,
        timeout: float = 1.0,
        motion: MotionConfig | None = None,
    ) -> "DrawCoreController":
        devices = discover_devices()
        if not devices:
            raise ConnectionError("No DrawCore-compatible devices were found.")
        return cls.connect(devices[0].port, timeout=timeout, motion=motion)

    def __enter__(self) -> "DrawCoreController":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def port_name(self) -> str | None:
        return getattr(self._transport, "port_name", None)

    def close(self) -> None:
        self._transport.close()

    def raw_command(self, command: str) -> None:
        self._transport.command(command)

    def raw_query(self, command: str) -> str:
        return self._transport.query(command)

    def get_firmware_version(self) -> str:
        return self._transport.query("V").strip()

    def get_nickname(self) -> str | None:
        result = self._transport.query("$QT").strip()
        return result or None

    def get_status(self) -> str | None:
        result = self._transport.query("?").strip()
        return result or None

    def get_device_info(self) -> DeviceInfo:
        return DeviceInfo(
            port=self.port_name,
            firmware=self.get_firmware_version(),
            nickname=self.get_nickname(),
            input_voltage_ok=None,
            status=self.get_status(),
        )

    def pen_up(self) -> None:
        self._transport.command(
            f"G1G90 Z{self.motion.pen_up_position}F{self.motion.feed_rate_pen_up}"
        )

    def pen_down(self) -> None:
        self._transport.command(
            f"G1G90 Z{self.motion.pen_down_position}F{self.motion.feed_rate_pen_down}"
        )

    def move_relative(
        self,
        *,
        x_inches: float = 0.0,
        y_inches: float = 0.0,
        x_mm: float | None = None,
        y_mm: float | None = None,
        feed_rate: int | None = None,
    ) -> None:
        if x_mm is None:
            x_mm = x_inches * 25.4
        if y_mm is None:
            y_mm = y_inches * 25.4
        if x_mm == 0.0 and y_mm == 0.0:
            return
        if feed_rate is None:
            feed_rate = self.motion.feed_rate_xy
        self._transport.command(f"G1G91X{x_mm}Y{y_mm}F{feed_rate}")

    def home(self) -> None:
        self._transport.home()
