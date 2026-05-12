from pydrawcore.models import CalibrationModel, CalibrationSample, MotionConfig
from pydrawcore.program import ProgramError, parse_program, run_program


class FakeProgramController:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float | None, float | None, int | None]] = []

    def home(self) -> None:
        self.calls.append(("home", None, None, None))

    def pen_up(self) -> None:
        self.calls.append(("pen_up", None, None, None))

    def pen_down(self) -> None:
        self.calls.append(("pen_down", None, None, None))

    def move_relative(self, *, x_mm: float = 0.0, y_mm: float = 0.0, feed_rate=None) -> None:
        self.calls.append(("move_relative", x_mm, y_mm, feed_rate))

    def dwell(self, milliseconds: int | float) -> None:
        self.calls.append(("dwell", float(milliseconds), None, None))


def _motion_with_calibration() -> MotionConfig:
    return MotionConfig(
        line_width_calibration=CalibrationModel.fit(
            [
                CalibrationSample(parameter_value=400.0, measured_value=0.9),
                CalibrationSample(parameter_value=800.0, measured_value=0.5),
            ]
        ),
        blot_delay_calibration=CalibrationModel.fit(
            [
                CalibrationSample(parameter_value=50.0, measured_value=0.5),
                CalibrationSample(parameter_value=150.0, measured_value=1.1),
            ]
        ),
    )


def test_parse_program_supports_repeat_blocks() -> None:
    program = parse_program("REPEAT 2\nFORWARD 10\nRIGHT 90\nEND\n")

    assert len(program.commands) == 1
    assert program.commands[0].name == "REPEAT"
    assert program.commands[0].values == (2,)
    assert [child.name for child in program.commands[0].children] == ["FORWARD", "RIGHT"]


def test_run_program_uses_calibrated_width_and_blot_dwell() -> None:
    controller = FakeProgramController()

    run_program(
        controller,
        _motion_with_calibration(),
        "MOVE 10 5\nFORWARD 20 WIDTH 0.7\nBLOT 0.8\n",
    )

    assert controller.calls == [
        ("pen_up", None, None, None),
        ("move_relative", 10.0, 5.0, 1200),
        ("pen_down", None, None, None),
        ("move_relative", 20.0, 0.0, 600),
        ("pen_up", None, None, None),
        ("pen_down", None, None, None),
        ("dwell", 100.0, None, None),
        ("pen_up", None, None, None),
    ]


def test_run_program_rejects_out_of_range_width() -> None:
    controller = FakeProgramController()

    try:
        run_program(controller, _motion_with_calibration(), "FORWARD 5 WIDTH 1.2\n")
    except ProgramError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ProgramError for width outside calibration range")

    assert "Line 1" in message
    assert "calibrated maximum" in message