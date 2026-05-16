from __future__ import annotations

from collections import deque

import pytest

from pydrawcore.exceptions import ProtocolError
from pydrawcore.transport import DrawCoreTransport


class FakeSerial:
    def __init__(self, responses: list[str]) -> None:
        self.responses = deque(response.encode("ascii") for response in responses)
        self.writes: list[bytes] = []
        self.timeout = 1.0
        self.is_open = True

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    def readline(self) -> bytes:
        if self.responses:
            return self.responses.popleft()
        return b""

    def reset_input_buffer(self) -> None:
        return None

    def close(self) -> None:
        self.is_open = False


def _make_transport(responses: list[str]) -> tuple[DrawCoreTransport, FakeSerial]:
    transport = object.__new__(DrawCoreTransport)
    serial = FakeSerial(responses)
    transport._serial = serial
    transport._port_name = "COM_TEST"
    return transport, serial


def test_query_status_does_not_expect_trailing_ok() -> None:
    transport, serial = _make_transport(["Idle\r\n"])

    assert transport.query("?") == "Idle\r\n"
    assert serial.writes == [b"?\r"]


def test_query_status_ignores_stray_ok_before_status_line() -> None:
    transport, serial = _make_transport(["ok\r\n", "<Idle|MPos:0.000,0.000,0.000>\r\n"])

    assert transport.query("?") == "<Idle|MPos:0.000,0.000,0.000>\r\n"
    assert serial.writes == [b"?\r"]


def test_home_unlocks_alarm_and_waits_for_idle() -> None:
    transport, serial = _make_transport(
        [
            "Alarm\r\n",
            "ok\r\n",
            "ok\r\n",
            "Run\r\n",
            "Idle\r\n",
        ]
    )

    transport.home()

    assert serial.writes == [b"?\r", b"$X\r", b"$H\r", b"?\r", b"?\r"]


def test_home_reports_controller_state_when_grbl_rejects_homing() -> None:
    transport, serial = _make_transport(["Idle\r\n", "error:8\r\n", "Jog\r\n"])

    with pytest.raises(ProtocolError, match="Cannot home while controller status is 'Jog'"):
        transport.home()

    assert serial.writes == [b"?\r", b"$H\r", b"?\r"]


def test_motion_command_does_not_poll_for_idle_after_ok() -> None:
    transport, serial = _make_transport(["ok\r\n"])

    transport.command("G1G90X10.0Y-5.0F3000")

    assert serial.writes == [b"G1G90X10.0Y-5.0F3000\r"]


def test_wait_until_idle_polls_until_status_is_idle() -> None:
    transport, serial = _make_transport(["Run\r\n", "ok\r\n", "<Idle|MPos:0.000,0.000,0.000>\r\n"])

    transport.wait_until_idle(timeout=1.0)

    assert serial.writes == [b"?\r", b"?\r"]


def test_non_motion_command_does_not_poll_for_idle() -> None:
    transport, serial = _make_transport(["ok\r\n"])

    transport.command("$X")

    assert serial.writes == [b"$X\r"]