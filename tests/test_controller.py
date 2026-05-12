import pydrawcore
from pydrawcore.controller import DrawCoreController
from pydrawcore.models import MotionConfig, WorkspaceBounds


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

    controller.move_relative(x_mm=25.4, y_mm=12.7, feed_rate=1200)

    assert transport.commands == ["G1G91X25.4Y-12.7F1200"]


def test_pen_up_and_down_emit_drawcore_commands() -> None:
    transport = FakeTransport()
    controller = DrawCoreController(transport, motion=MotionConfig())

    controller.pen_up()
    controller.pen_down()

    assert transport.commands == [
        "G1G90 Z0.5F5000",
        "G1G90 Z5.0F5000",
    ]


def test_move_pen_uses_explicit_position_and_inferred_feed_rate() -> None:
    transport = FakeTransport()
    controller = DrawCoreController(transport, motion=MotionConfig())

    controller.move_pen(0.0)
    controller.move_pen(6.0)

    assert transport.commands == [
        "G1G90 Z0.0F5000",
        "G1G90 Z6.0F5000",
    ]


def test_move_pen_relative_uses_signed_delta() -> None:
    transport = FakeTransport()
    controller = DrawCoreController(transport, motion=MotionConfig())

    controller.move_pen_relative(0.5)
    controller.move_pen_relative(-0.25)

    assert transport.commands == [
        "G1G91 Z0.5F5000",
        "G1G91 Z-0.25F5000",
    ]


def test_dwell_formats_native_pause_command() -> None:
    transport = FakeTransport()
    controller = DrawCoreController(transport, motion=MotionConfig())

    controller.dwell(150)

    assert transport.commands == ["G4 P0.150"]


def test_move_pen_clamps_to_safe_drawcore_range() -> None:
    transport = FakeTransport()
    controller = DrawCoreController(transport, motion=MotionConfig())

    controller.move_pen(-1.0)
    controller.move_pen(12.0)

    assert transport.commands == [
        "G1G90 Z0.0F5000",
        "G1G90 Z10.0F5000",
    ]


def test_get_device_info_reads_queries() -> None:
    transport = FakeTransport()
    controller = DrawCoreController(transport)

    info = controller.get_device_info()

    assert info.port == "COM_TEST"
    assert info.nickname == "writer-01"
    assert info.inferred_model is None
    assert info.status == "Idle"


def test_get_inferred_model_uses_rig_nickname() -> None:
    transport = FakeTransport()
    transport.query = lambda command: {
        "V": "DrawCore V2.22.20260207\n",
        "$QT": "rig-v3a3-01\n",
        "?": "Idle\n",
    }[command]
    controller = DrawCoreController(transport)

    assert controller.get_inferred_model() == "v3a3"


def test_drawcore_home_uses_native_home_command() -> None:
    transport = FakeTransport()
    controller = DrawCoreController(transport)

    controller.home()

    assert transport.commands == []
    assert transport.home_calls == 1


def test_package_exports_workspace_helpers() -> None:
    bounds = pydrawcore.workspace_bounds_for_model("default")

    assert isinstance(bounds, WorkspaceBounds)
    assert pydrawcore.WorkspaceBounds is WorkspaceBounds
    assert pydrawcore.infer_model_from_nickname("rig-v3a3-01") == "v3a3"
