from pydrawcore.models import CalibrationModel, CalibrationSample, MotionConfig, WorkspaceBounds
from pydrawcore.program import ProgramError, ProgramRunner, TurtleState, check_program_fits_workspace, export_preview_svg, parse_program, preview_program, run_program


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

    def move_absolute(self, *, x_mm: float = 0.0, y_mm: float = 0.0, feed_rate=None) -> None:
        self.calls.append(("move_absolute", x_mm, y_mm, feed_rate))

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


def test_parse_program_supports_setwidth() -> None:
    program = parse_program("SETWIDTH 0.7\nFORWARD 10\nSETWIDTH NONE\nBACK 5\n")

    assert [command.name for command in program.commands] == ["SETWIDTH", "FORWARD", "SETWIDTH", "BACK"]
    assert program.commands[0].values == (0.7,)
    assert program.commands[2].values == (None,)


def test_run_program_uses_calibrated_width_and_blot_dwell() -> None:
    controller = FakeProgramController()

    run_program(
        controller,
        _motion_with_calibration(),
        "MOVE 10 5\nFORWARD 20 WIDTH 0.7\nBLOT 0.8\n",
    )

    assert controller.calls == [
        ("pen_up", None, None, None),      # run() start: raise pen
        ("move_absolute", 0.0, 0.0, 3000),
        ("pen_up", None, None, None),      # MOVE: _move_to raises pen
        ("move_absolute", 10.0, 5.0, 3000),
        ("pen_down", None, None, None),
        ("move_absolute", 30.0, 5.0, 600),
        ("pen_up", None, None, None),
        ("pen_down", None, None, None),
        ("dwell", 100.0, None, None),
        ("pen_up", None, None, None),
        ("pen_up", None, None, None),      # run() end: raise pen
        ("move_absolute", 0.0, 0.0, 3000),
    ]


def test_run_program_uses_setwidth_as_default_draw_width() -> None:
    controller = FakeProgramController()

    run_program(
        controller,
        _motion_with_calibration(),
        "SETWIDTH 0.7\nFORWARD 20\nLINE 40 0\nSETWIDTH NONE\nBACK 10\n",
    )

    assert controller.calls == [
        ("pen_up", None, None, None),      # run() start: raise pen
        ("move_absolute", 0.0, 0.0, 3000),
        ("pen_down", None, None, None),
        ("move_absolute", 20.0, 0.0, 600),
        ("pen_up", None, None, None),
        ("pen_down", None, None, None),
        ("move_absolute", 40.0, 0.0, 600),
        ("pen_up", None, None, None),
        ("pen_down", None, None, None),
        ("move_absolute", 30.0, 0.0, 1200),
        ("pen_up", None, None, None),
        ("pen_up", None, None, None),      # run() end: raise pen
        ("move_absolute", 0.0, 0.0, 3000),
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


def test_runner_returns_to_plotting_origin_with_pen_up() -> None:
    controller = FakeProgramController()
    runner = ProgramRunner(
        controller=controller,
        motion=_motion_with_calibration(),
        state=TurtleState(),
    )

    runner.run(parse_program("MOVE 10 5\nFORWARD 20 WIDTH 0.7\n"))
    runner.return_to_origin()

    assert controller.calls == [
        ("pen_up", None, None, None),      # run() start: raise pen
        ("move_absolute", 0.0, 0.0, 3000),
        ("pen_up", None, None, None),      # MOVE: _move_to raises pen
        ("move_absolute", 10.0, 5.0, 3000),
        ("pen_down", None, None, None),
        ("move_absolute", 30.0, 5.0, 600),
        ("pen_up", None, None, None),
        ("pen_up", None, None, None),      # run() end: raise pen
        ("move_absolute", 0.0, 0.0, 3000),
        # return_to_origin() called explicitly – already at (0,0) so no-op
    ]


def test_run_program_applies_workspace_origin_offset_to_machine_moves() -> None:
    controller = FakeProgramController()

    run_program(
        controller,
        _motion_with_calibration(),
        "MOVE 10 5\nFORWARD 20 WIDTH 0.7\n",
        workspace_bounds=WorkspaceBounds(
            model="test",
            width_mm=100.0,
            height_mm=100.0,
            origin_offset_x_mm=12.0,
            origin_offset_y_mm=7.0,
        ),
    )

    assert controller.calls == [
        ("pen_up", None, None, None),
        ("move_absolute", 12.0, 7.0, 3000),
        ("pen_up", None, None, None),
        ("move_absolute", 22.0, 12.0, 3000),
        ("pen_down", None, None, None),
        ("move_absolute", 42.0, 12.0, 600),
        ("pen_up", None, None, None),
        ("pen_up", None, None, None),
        ("move_absolute", 12.0, 7.0, 3000),
    ]


def test_preview_program_records_operations_and_estimated_widths() -> None:
    preview = preview_program(
        _motion_with_calibration(),
        "SETWIDTH 0.7\nMOVE 10 5\nFORWARD 20\nBLOT 0.8\n",
        return_to_origin=True,
    )

    operations = preview.to_dict()["operations"]
    assert [operation["kind"] for operation in operations] == ["travel", "draw", "blot", "travel"]
    assert operations[1]["estimated_width_mm"] == 0.7
    assert operations[2]["estimated_blot_size_mm"] == 0.8


def test_export_preview_svg_writes_svg_file(tmp_path) -> None:
    preview = preview_program(_motion_with_calibration(), "SETWIDTH 0.7\nFORWARD 20\n", return_to_origin=True)
    output_path = tmp_path / "preview.svg"

    resolved_path = export_preview_svg(preview, output_path)

    assert resolved_path == output_path.resolve()
    svg_text = output_path.read_text(encoding="utf-8")
    assert "<svg" in svg_text
    assert "<line" in svg_text


# ---------------------------------------------------------------------------
# Workspace bounds safety checks
# ---------------------------------------------------------------------------

def _small_workspace() -> WorkspaceBounds:
    """50 mm × 50 mm workspace for bounds tests."""
    return WorkspaceBounds("test", 50.0, 50.0)


def test_check_program_fits_workspace_passes_when_inside() -> None:
    """A program that stays within the workspace raises no error."""
    check_program_fits_workspace(
        _motion_with_calibration(),
        "FORWARD 40\n",
        _small_workspace(),
    )


def test_check_program_fits_workspace_raises_when_right_edge_exceeded() -> None:
    """Exceeding the right edge raises ProgramError naming the violation."""
    try:
        check_program_fits_workspace(
            _motion_with_calibration(),
            "FORWARD 60\n",
            _small_workspace(),
        )
    except ProgramError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ProgramError for right-edge violation")

    assert "right edge" in message
    assert "50.00 mm" in message


def test_check_program_fits_workspace_raises_when_top_edge_exceeded() -> None:
    """Exceeding the top edge raises ProgramError naming the violation."""
    try:
        check_program_fits_workspace(
            _motion_with_calibration(),
            "SETHEADING 90\nFORWARD 60\n",
            _small_workspace(),
        )
    except ProgramError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ProgramError for top-edge violation")

    assert "top edge" in message


def test_check_program_fits_workspace_raises_when_negative_x() -> None:
    """Moving into negative X raises ProgramError for the left edge."""
    try:
        check_program_fits_workspace(
            _motion_with_calibration(),
            "SETHEADING 180\nFORWARD 10\n",
            _small_workspace(),
        )
    except ProgramError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ProgramError for left-edge violation")

    assert "left edge" in message


def test_check_program_fits_workspace_raises_when_negative_y() -> None:
    """Moving into negative Y raises ProgramError for the bottom edge."""
    try:
        check_program_fits_workspace(
            _motion_with_calibration(),
            "SETHEADING 270\nFORWARD 10\n",
            _small_workspace(),
        )
    except ProgramError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ProgramError for bottom-edge violation")

    assert "bottom edge" in message


def test_run_program_with_workspace_bounds_raises_before_any_hardware_call() -> None:
    """run_program rejects an out-of-bounds program before touching the controller."""
    controller = FakeProgramController()

    try:
        run_program(
            controller,
            _motion_with_calibration(),
            "FORWARD 60\n",
            workspace_bounds=_small_workspace(),
        )
    except ProgramError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ProgramError for out-of-bounds program")

    assert "right edge" in message
    # No hardware calls must have been made
    assert controller.calls == []


def test_run_program_with_workspace_bounds_executes_when_inside() -> None:
    """run_program proceeds normally when the program fits the workspace."""
    controller = FakeProgramController()

    run_program(
        controller,
        _motion_with_calibration(),
        "FORWARD 40\n",
        workspace_bounds=_small_workspace(),
    )

    assert any(call[0] == "move_absolute" for call in controller.calls)


def test_check_program_fits_workspace_circle_exceeds_bounds() -> None:
    """A circle whose perimeter exits the workspace is rejected."""
    # Origin at (0,0), circle radius 30 mm → right edge at 30 mm, exceeds 20 mm workspace.
    small = WorkspaceBounds("test", 20.0, 20.0)
    try:
        check_program_fits_workspace(
            _motion_with_calibration(),
            "CIRCLE 60\n",
            small,
        )
    except ProgramError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ProgramError for circle exceeding workspace")

    assert "workspace" in message