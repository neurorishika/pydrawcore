from pydrawcore.controller import DrawCoreController
from pydrawcore.models import MotionConfig


class FakeTransport:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.queries: list[str] = []
        self.port_name = "COM_TEST"
        self.home_calls = 0

    def close(self) -> None:
        return None

    def command(self, command: str) -> None:
        self.commands.append(command)

    def query(self, command: str) -> str:
        self.queries.append(command)
        responses = {
            "V": "DrawCore V2.22.20260207\n",
            "$QT": "writer-01\n",
            "?": "Idle\n",
        }
        return responses[command]

    def home(self) -> None:
        self.home_calls += 1


def test_move_relative_formats_native_drawcore_command() -> None:
    transport = FakeTransport()
    controller = DrawCoreController(transport)

    controller.move_relative(x_mm=25.4, y_mm=0.0, feed_rate=1200)

    assert transport.commands == ["G1G91X25.4Y0.0F1200"]


def test_pen_up_and_down_emit_drawcore_commands() -> None:
    transport = FakeTransport()
    controller = DrawCoreController(transport, motion=MotionConfig())

    controller.pen_up()
    controller.pen_down()

    assert transport.commands == [
        "G1G90 Z60F1200",
        "G1G90 Z30F600",
    ]


def test_get_device_info_reads_queries() -> None:
    transport = FakeTransport()
    controller = DrawCoreController(transport)

    info = controller.get_device_info()

    assert info.port == "COM_TEST"
    assert info.nickname == "writer-01"
    assert info.status == "Idle"


def test_drawcore_home_uses_native_home_command() -> None:
    transport = FakeTransport()
    controller = DrawCoreController(transport)

    controller.home()

    assert transport.commands == []
    assert transport.home_calls == 1
