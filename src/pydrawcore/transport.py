from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Final

import serial

from .exceptions import ConnectionError, DeviceNotReadyError, ProtocolError
from .protocol import ensure_cr, parse_ok, parse_version


_QUERY_WITHOUT_TRAILING_OK: Final[set[str]] = {"V", "I", "A", "MR", "PI", "QM"}


class BaseTransport(ABC):
    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def command(self, command: str, *, response_timeout: float | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def query(self, command: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def home(self) -> None:
        raise NotImplementedError


class DrawCoreTransport(BaseTransport):
    def __init__(self, port: str, timeout: float = 1.0, baudrate: int = 115200):
        self._port_name = port
        try:
            self._serial = serial.Serial()
            self._serial.port = port
            self._serial.baudrate = baudrate
            self._serial.timeout = timeout
            self._serial.rts = False
            self._serial.dtr = False
            self._serial.open()
        except serial.SerialException as exc:
            raise ConnectionError(f"Unable to open serial port {port!r}") from exc

        self._wake_device()
        version = parse_version(self.query("V"))
        if not version.startswith("DrawCore"):
            self.close()
            raise ConnectionError(f"Port {port!r} did not identify as a DrawCore controller.")

        try:
            status = self.query("?")
        except ProtocolError:
            status = ""
        if "Alarm" in status:
            self.command("$X")

    @property
    def port_name(self) -> str:
        return self._port_name

    def close(self) -> None:
        if getattr(self, "_serial", None) is not None and self._serial.is_open:
            self._serial.close()

    def command(self, command: str, *, response_timeout: float | None = None) -> None:
        normalized = ensure_cr(command)
        response = self._round_trip(normalized, response_timeout=response_timeout)
        parse_ok(response, normalized.rstrip())

    def query(self, command: str) -> str:
        normalized = ensure_cr(command)
        data = self._round_trip(normalized)
        head = normalized.split(",", 1)[0].strip().upper().rstrip("\r")
        if head not in _QUERY_WITHOUT_TRAILING_OK:
            self._readline(expect_non_empty=True)
        return data

    def home(self) -> None:
        self.command("$H")

    def _wake_device(self) -> None:
        self._ensure_open()
        self._serial.write(b"$B\r")
        self._serial.readline()
        self._serial.readline()
        self._serial.reset_input_buffer()

    def _round_trip(self, command: str, *, response_timeout: float | None = None) -> str:
        self._ensure_open()
        original_timeout = self._serial.timeout
        if response_timeout is not None:
            self._serial.timeout = response_timeout
        try:
            self._serial.write(command.encode("ascii"))
        except serial.SerialException as exc:
            raise ConnectionError(f"Failed while sending {command!r}") from exc
        try:
            return self._readline(expect_non_empty=True)
        finally:
            if response_timeout is not None:
                self._serial.timeout = original_timeout

    def _readline(self, expect_non_empty: bool) -> str:
        self._ensure_open()
        attempts = 0
        response = self._serial.readline().decode("ascii", errors="replace")
        while not response and attempts < 10:
            response = self._serial.readline().decode("ascii", errors="replace")
            attempts += 1
        if expect_non_empty and not response:
            raise ProtocolError("Timed out waiting for device response.")
        return response

    def _ensure_open(self) -> None:
        if getattr(self, "_serial", None) is None or not self._serial.is_open:
            raise DeviceNotReadyError("Serial transport is not open.")


def open_transport(port: str, *, timeout: float = 1.0) -> BaseTransport:
    return DrawCoreTransport(port=port, timeout=timeout)
