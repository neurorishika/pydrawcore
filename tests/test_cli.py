import json
from pathlib import Path

from pydrawcore import cli
from pydrawcore.models import CalibrationModel, CalibrationSample, DeviceInfo, MotionConfig, workspace_bounds_for_model


class FakeCalibrationController:
    def __init__(self) -> None:
        self.positions: list[float] = []
        self.moves: list[tuple[float, float]] = []
        self.raw_commands: list[str] = []
        self.home_called = False

    def __enter__(self) -> "FakeCalibrationController":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def move_pen(self, position: float, *, feed_rate: int | None = None) -> None:
        self.positions.append(position)

    def raw_command(self, command: str) -> None:
        self.raw_commands.append(command)

    def move_relative(self, *, x_mm: float = 0.0, y_mm: float = 0.0, feed_rate: int | None = None) -> None:
        self.moves.append((x_mm, y_mm))

    def pen_up(self) -> None:
        return None

    def home(self) -> None:
        self.home_called = True


def test_calibrate_pen_writes_motion_profile(monkeypatch, tmp_path, capsys) -> None:
    controller = FakeCalibrationController()
    answers = iter(["", "12", "7", "y", "", "", "y", "", "y"])
    output_path = tmp_path / "motion.json"
    workspace_path = tmp_path / "workspace.json"

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    exit_code = cli.main(
        [
            "calibrate-pen",
            "--output",
            str(output_path),
            "--workspace-config",
            str(workspace_path),
            "--midpoint",
            "5.0",
            "--step",
            "0.5",
        ]
    )

    assert exit_code == 0
    assert controller.home_called is True
    assert controller.moves == [(12.0, 7.0)]
    assert controller.positions == [5.0, 5.0, 5.0, 5.5, 5.0, 5.0, 4.5]
    assert controller.raw_commands == ["G4 P0.15", "G4 P0.15"]
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "feed_rate_xy": 1200,
        "feed_rate_pen_up": 5000,
        "feed_rate_pen_down": 5000,
        "pen_up_position": 4.5,
        "pen_down_position": 5.5,
    }
    assert json.loads(workspace_path.read_text(encoding="utf-8")) == {
        "model": "default",
        "width_mm": workspace_bounds_for_model("default").width_mm,
        "height_mm": workspace_bounds_for_model("default").height_mm,
        "origin_offset_x_mm": 12.0,
        "origin_offset_y_mm": 7.0,
    }
    output = capsys.readouterr().out
    assert "Saved motion profile" in output
    assert "Saved workspace profile" in output


def test_calibrate_pen_uses_safe_limits_when_user_keeps_advancing(monkeypatch, tmp_path, capsys) -> None:
    controller = FakeCalibrationController()
    answers = iter(["", "0", "0", "y", "", "", "", "", "", "", "", "", "", "", "", "", ""])
    config_dir = tmp_path / ".drawcore"

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    exit_code = cli.main(["calibrate-pen", "--config-dir", str(config_dir), "--midpoint", "5.0", "--step", "1.0"])

    assert exit_code == 0
    assert 10.0 in controller.positions
    assert 0.0 in controller.positions
    output = capsys.readouterr().out
    assert "Reached the safe lower limit" in output
    assert "Reached the safe upper limit" in output


def test_pen_up_uses_motion_profile_from_json(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}
    motion_config_path = tmp_path / "motion.json"
    motion_config_path.write_text(
        json.dumps(
            {
                "feed_rate_xy": 1200,
                "feed_rate_pen_up": 900,
                "feed_rate_pen_down": 500,
                "pen_up_position": 77,
                "pen_down_position": 21,
            }
        ),
        encoding="utf-8",
    )

    class FakePenController:
        def __init__(self, motion) -> None:
            self.motion = motion
            captured["motion"] = motion
            captured["pen_up_called"] = False

        def __enter__(self) -> "FakePenController":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def pen_up(self) -> None:
            captured["pen_up_called"] = True

    monkeypatch.setattr(
        cli.DrawCoreController,
        "auto_connect",
        lambda motion=None: FakePenController(motion),
    )

    exit_code = cli.main(["pen-up", "--motion-config", str(motion_config_path)])

    assert exit_code == 0
    assert captured["pen_up_called"] is True
    assert captured["motion"].pen_up_position == 10.0
    assert captured["motion"].pen_down_position == 10.0
    assert captured["motion"].feed_rate_pen_up == 900


def test_pen_up_uses_default_profile_from_config_dir(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}
    config_dir = tmp_path / ".drawcore"
    config_dir.mkdir()
    (config_dir / "motion.json").write_text(
        json.dumps(
            {
                "feed_rate_xy": 1200,
                "feed_rate_pen_up": 1100,
                "feed_rate_pen_down": 700,
                "pen_up_position": 1.25,
                "pen_down_position": 4.75,
            }
        ),
        encoding="utf-8",
    )

    class FakePenController:
        def __init__(self, motion) -> None:
            captured["motion"] = motion

        def __enter__(self) -> "FakePenController":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def pen_up(self) -> None:
            captured["pen_up_called"] = True

    monkeypatch.setattr(
        cli.DrawCoreController,
        "auto_connect",
        lambda motion=None: FakePenController(motion),
    )

    exit_code = cli.main(["pen-up", "--config-dir", str(config_dir)])

    assert exit_code == 0
    assert captured["pen_up_called"] is True
    assert captured["motion"].pen_up_position == 1.25
    assert captured["motion"].pen_down_position == 4.75


def test_calibrate_pen_saves_default_profile_in_config_dir(monkeypatch, tmp_path, capsys) -> None:
    controller = FakeCalibrationController()
    answers = iter(["", "9", "6", "y", "", "", "y", "", "y"])
    config_dir = tmp_path / ".drawcore"

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    exit_code = cli.main(["calibrate-pen", "--config-dir", str(config_dir), "--midpoint", "5.0", "--step", "0.5"])

    assert exit_code == 0
    saved_profile = config_dir / "motion.json"
    assert saved_profile.exists()
    assert json.loads(saved_profile.read_text(encoding="utf-8")) == {
        "feed_rate_xy": 1200,
        "feed_rate_pen_up": 5000,
        "feed_rate_pen_down": 5000,
        "pen_up_position": 4.5,
        "pen_down_position": 5.5,
    }
    saved_workspace = config_dir / "workspace.json"
    assert json.loads(saved_workspace.read_text(encoding="utf-8")) == {
        "model": "default",
        "width_mm": workspace_bounds_for_model("default").width_mm,
        "height_mm": workspace_bounds_for_model("default").height_mm,
        "origin_offset_x_mm": 9.0,
        "origin_offset_y_mm": 6.0,
    }
    output = capsys.readouterr().out
    assert str(saved_profile.resolve()) in output
    assert str(saved_workspace.resolve()) in output


class FakeBoundsController:
    def __init__(self, *, port_name: str = "COM4", inferred_model: str | None = None) -> None:
        self.calls: list[tuple[str, float | None, float | None]] = []
        self.port_name = port_name
        self._inferred_model = inferred_model

    def __enter__(self) -> "FakeBoundsController":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def home(self) -> None:
        self.calls.append(("home", None, None))

    def pen_up(self) -> None:
        self.calls.append(("pen_up", None, None))

    def pen_down(self) -> None:
        self.calls.append(("pen_down", None, None))

    def move_relative(self, *, x_mm: float = 0.0, y_mm: float = 0.0, feed_rate=None) -> None:
        self.calls.append(("move_relative", x_mm, y_mm))

    def raw_command(self, command: str) -> None:
        self.calls.append(("raw_command", None, None))

    def get_inferred_model(self) -> str | None:
        return self._inferred_model


class FakeCommandController:
    def __init__(self, *, port_name: str = "COM4") -> None:
        self.port_name = port_name
        self.pen_down_called = False
        self.pen_up_called = False
        self.home_called = False
        self.home_calls = 0
        self.raw_commands: list[str] = []
        self.raw_queries: list[str] = []
        self.dwell_calls: list[float] = []
        self.moves: list[tuple[float, float, int | None]] = []

    def __enter__(self) -> "FakeCommandController":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def pen_down(self) -> None:
        self.pen_down_called = True

    def pen_up(self) -> None:
        self.pen_up_called = True

    def home(self) -> None:
        self.home_called = True
        self.home_calls += 1

    def dwell(self, milliseconds: int | float) -> None:
        self.dwell_calls.append(float(milliseconds))

    def raw_command(self, command: str) -> None:
        self.raw_commands.append(command)

    def raw_query(self, command: str) -> str:
        self.raw_queries.append(command)
        return "DrawCore V2.22.20260207\n"

    def move_relative(self, *, x_mm: float = 0.0, y_mm: float = 0.0, feed_rate=None) -> None:
        self.moves.append((x_mm, y_mm, feed_rate))

    def get_device_info(self):
        return DeviceInfo(
            port=self.port_name,
            firmware="DrawCore V2.22.20260207",
            nickname=None,
            inferred_model=None,
            status="Idle",
        )


def test_mark_bounds_requires_saved_workspace_profile_when_homing(monkeypatch, tmp_path) -> None:
    controller = FakeBoundsController()
    config_dir = tmp_path / ".drawcore"

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)

    try:
        cli.main(["mark-bounds", "--model", "default", "--inset-mm", "5.0", "--config-dir", str(config_dir)])
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("mark-bounds should require a saved workspace profile when homing")

    assert controller.calls == []
    assert "Run calibrate-pen first" in message


def test_discover_prints_connected_devices(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "discover_devices",
        lambda: [
            cli.DiscoveredDevice(
                port="COM4",
                description="USB Serial Device (COM4)",
                hwid="USB VID:PID=1A86:8040 SER=01",
            )
        ],
    )

    exit_code = cli.main(["discover"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output[0]["port"] == "COM4"


def test_info_prints_device_metadata_and_resolution(monkeypatch, tmp_path, capsys) -> None:
    controller = FakeCommandController()
    config_dir = tmp_path / ".drawcore"
    config_dir.mkdir()
    (config_dir / "devices.json").write_text(
        json.dumps({"USB VID:PID=1A86:8040 SER=01": "v3a3"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)
    monkeypatch.setattr(
        cli,
        "discover_devices",
        lambda: [type("Device", (), {"port": "COM4", "description": "USB Serial", "hwid": "USB VID:PID=1A86:8040 SER=01"})()],
    )

    exit_code = cli.main(["info", "--config-dir", str(config_dir)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["firmware"] == "DrawCore V2.22.20260207"
    assert output["remembered_model"] == "v3a3"
    assert output["resolved_model"] == "v3a3"


def test_pen_down_calls_controller(monkeypatch) -> None:
    controller = FakeCommandController()

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)

    exit_code = cli.main(["pen-down"])

    assert exit_code == 0
    assert controller.pen_down_called is True


def test_move_relative_calls_controller_with_requested_units(monkeypatch) -> None:
    controller = FakeCommandController()

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)

    exit_code = cli.main(["move-relative", "--x-mm", "10", "--y-mm", "5", "--feed-rate", "1500"])

    assert exit_code == 0
    assert controller.moves == [(10.0, 5.0, 1500)]


def test_home_calls_controller(monkeypatch) -> None:
    controller = FakeCommandController()

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)

    exit_code = cli.main(["home"])

    assert exit_code == 0
    assert controller.home_called is True


def test_raw_query_prints_controller_response(monkeypatch, capsys) -> None:
    controller = FakeCommandController()

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)

    exit_code = cli.main(["raw-query", "V"])

    assert exit_code == 0
    assert controller.raw_queries == ["V"]
    assert capsys.readouterr().out.strip() == "DrawCore V2.22.20260207"


def test_raw_command_calls_controller(monkeypatch) -> None:
    controller = FakeCommandController()

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)

    exit_code = cli.main(["raw-command", "$H"])

    assert exit_code == 0
    assert controller.raw_commands == ["$H"]


def test_run_program_dry_run_prints_normalized_commands(tmp_path, capsys) -> None:
    program_path = tmp_path / "pattern.draw"
    program_path.write_text("SETWIDTH 0.7\nFORWARD 10\nRIGHT 90\n", encoding="utf-8")

    exit_code = cli.main(["run-program", str(program_path), "--dry-run"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output == [
        {"line": 1, "command": "SETWIDTH", "values": [0.7], "children": []},
        {"line": 2, "command": "FORWARD", "values": [10.0, None], "children": []},
        {"line": 3, "command": "RIGHT", "values": [90.0], "children": []},
    ]


def test_run_program_executes_with_motion_profile(monkeypatch, tmp_path, capsys) -> None:
    controller = FakeCommandController()
    program_path = tmp_path / "pattern.draw"
    program_path.write_text("MOVE 10 5\nFORWARD 20 WIDTH 0.7\nBLOT 0.8\n", encoding="utf-8")
    motion_path = tmp_path / "motion.json"
    MotionConfig(
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
    ).to_file(motion_path)

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)

    exit_code = cli.main(["run-program", str(program_path), "--motion-config", str(motion_path)])

    assert exit_code == 0
    assert controller.pen_down_called is True
    assert controller.pen_up_called is True
    assert controller.home_calls == 0
    assert controller.moves == [
        (10.0, 5.0, 1200),
        (20.0, 0.0, 600),
        (-30.0, -5.0, 1200),
    ]
    assert controller.dwell_calls == [100.0]
    output = json.loads(capsys.readouterr().out)
    assert output["commands"] == 3


def test_run_program_returns_to_origin_when_program_fails(monkeypatch, tmp_path) -> None:
    controller = FakeCommandController()
    program_path = tmp_path / "pattern.draw"
    program_path.write_text("FORWARD 5 WIDTH 1.2\n", encoding="utf-8")
    motion_path = tmp_path / "motion.json"
    MotionConfig(
        line_width_calibration=CalibrationModel.fit(
            [
                CalibrationSample(parameter_value=400.0, measured_value=0.9),
                CalibrationSample(parameter_value=800.0, measured_value=0.5),
            ]
        )
    ).to_file(motion_path)

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)

    try:
        cli.main(["run-program", str(program_path), "--motion-config", str(motion_path)])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("Expected run-program to fail for out-of-range width")

    assert controller.pen_up_called is True
    assert controller.home_calls == 0
    assert controller.moves == []


def test_run_program_preview_outputs_motion_plan(tmp_path, capsys) -> None:
    program_path = tmp_path / "pattern.draw"
    motion_path = tmp_path / "motion.json"
    program_path.write_text("SETWIDTH 0.7\nMOVE 10 5\nFORWARD 20\nBLOT 0.8\n", encoding="utf-8")
    MotionConfig(
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
    ).to_file(motion_path)

    exit_code = cli.main(["run-program", str(program_path), "--motion-config", str(motion_path), "--preview"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["commands"] == 4
    assert [operation["kind"] for operation in output["preview"]["operations"]] == ["travel", "draw", "blot", "travel"]


def test_run_program_export_svg_writes_preview_file(tmp_path, capsys) -> None:
    program_path = tmp_path / "pattern.draw"
    motion_path = tmp_path / "motion.json"
    svg_path = tmp_path / "preview.svg"
    program_path.write_text("SETWIDTH 0.7\nFORWARD 20\n", encoding="utf-8")
    MotionConfig(
        line_width_calibration=CalibrationModel.fit(
            [
                CalibrationSample(parameter_value=400.0, measured_value=0.9),
                CalibrationSample(parameter_value=800.0, measured_value=0.5),
            ]
        )
    ).to_file(motion_path)

    exit_code = cli.main(["run-program", str(program_path), "--motion-config", str(motion_path), "--export-svg", str(svg_path)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["svg_path"] == str(svg_path.resolve())
    assert "<svg" in svg_path.read_text(encoding="utf-8")


def test_mark_bounds_accepts_dimension_overrides_without_homing(monkeypatch) -> None:
    controller = FakeBoundsController()

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)

    exit_code = cli.main(
        [
            "mark-bounds",
            "--skip-home",
            "--width-mm",
            "100",
            "--height-mm",
            "80",
            "--inset-mm",
            "10",
        ]
    )

    bounds = workspace_bounds_for_model("default")
    assert exit_code == 0
    assert controller.calls[0] == ("pen_up", None, None)
    assert controller.calls == [
        ("pen_up", None, None),
        ("move_relative", 10.0, 10.0),
        ("pen_down", None, None),
        ("move_relative", 80.0, 0.0),
        ("move_relative", 0.0, 60.0),
        ("move_relative", -80.0, 0.0),
        ("move_relative", 0.0, -60.0),
        ("pen_up", None, None),
    ]


def test_mark_bounds_uses_model_workspace_and_inset_from_known_origin(monkeypatch, capsys) -> None:
    controller = FakeBoundsController()

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)

    exit_code = cli.main(["mark-bounds", "--model", "default", "--inset-mm", "5.0", "--skip-home"])

    bounds = workspace_bounds_for_model("default")
    assert exit_code == 0
    assert controller.calls == [
        ("pen_up", None, None),
        ("move_relative", 5.0, 5.0),
        ("pen_down", None, None),
        ("move_relative", bounds.width_mm - 10.0, 0.0),
        ("move_relative", 0.0, bounds.height_mm - 10.0),
        ("move_relative", -(bounds.width_mm - 10.0), 0.0),
        ("move_relative", 0.0, -(bounds.height_mm - 10.0)),
        ("pen_up", None, None),
    ]
    output = json.loads(capsys.readouterr().out)
    assert output["model"] == "default"


def test_mark_bounds_uses_saved_workspace_profile_by_default(monkeypatch, tmp_path) -> None:
    controller = FakeBoundsController()
    config_dir = tmp_path / ".drawcore"
    config_dir.mkdir()
    (config_dir / "workspace.json").write_text(
        json.dumps(
            {
                "model": "default",
                "width_mm": 120.0,
                "height_mm": 90.0,
                "origin_offset_x_mm": 12.0,
                "origin_offset_y_mm": 7.0,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)

    exit_code = cli.main(["mark-bounds", "--config-dir", str(config_dir), "--inset-mm", "10"])

    assert exit_code == 0
    assert controller.calls == [
        ("home", None, None),
        ("pen_up", None, None),
        ("move_relative", 12.0, 7.0),
        ("move_relative", 10.0, 10.0),
        ("pen_down", None, None),
        ("move_relative", 100.0, 0.0),
        ("move_relative", 0.0, 70.0),
        ("move_relative", -100.0, 0.0),
        ("move_relative", 0.0, -70.0),
        ("pen_up", None, None),
    ]


def test_mark_bounds_explicit_model_overrides_saved_workspace_profile(monkeypatch, tmp_path) -> None:
    controller = FakeBoundsController()
    config_dir = tmp_path / ".drawcore"
    config_dir.mkdir()
    (config_dir / "workspace.json").write_text(
        json.dumps(
            {
                "model": "default",
                "width_mm": 120.0,
                "height_mm": 90.0,
                "origin_offset_x_mm": 4.0,
                "origin_offset_y_mm": 6.0,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)

    exit_code = cli.main(
        [
            "mark-bounds",
            "--config-dir",
            str(config_dir),
            "--model",
            "v3a3",
            "--inset-mm",
            "10",
        ]
    )

    bounds = workspace_bounds_for_model("v3a3")
    assert exit_code == 0
    assert controller.calls == [
        ("home", None, None),
        ("pen_up", None, None),
        ("move_relative", 4.0, 6.0),
        ("move_relative", 10.0, 10.0),
        ("pen_down", None, None),
        ("move_relative", bounds.width_mm - 20.0, 0.0),
        ("move_relative", 0.0, bounds.height_mm - 20.0),
        ("move_relative", -(bounds.width_mm - 20.0), 0.0),
        ("move_relative", 0.0, -(bounds.height_mm - 20.0)),
        ("pen_up", None, None),
    ]


def test_calibrate_xy_saves_workspace_profile(monkeypatch, tmp_path, capsys) -> None:
    controller = FakeBoundsController()
    answers = iter(["", "", "y", "123.5", "", "", "y", "87.25"])
    config_dir = tmp_path / ".drawcore"
    config_dir.mkdir()
    (config_dir / "workspace.json").write_text(
        json.dumps(
            {
                "model": "default",
                "width_mm": workspace_bounds_for_model("default").width_mm,
                "height_mm": workspace_bounds_for_model("default").height_mm,
                "origin_offset_x_mm": 12.0,
                "origin_offset_y_mm": 7.0,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    exit_code = cli.main(["calibrate-xy", "--config-dir", str(config_dir), "--step-mm", "20", "--max-x-mm", "200", "--max-y-mm", "150"])

    assert exit_code == 0
    saved_profile = config_dir / "workspace.json"
    assert json.loads(saved_profile.read_text(encoding="utf-8")) == {
        "model": "default",
        "width_mm": 123.5,
        "height_mm": 87.25,
        "origin_offset_x_mm": 12.0,
        "origin_offset_y_mm": 7.0,
    }
    assert controller.calls == [
        ("home", None, None),
        ("pen_up", None, None),
        ("move_relative", 12.0, 7.0),
        ("pen_up", None, None),
        ("pen_down", None, None),
        ("raw_command", None, None),
        ("pen_up", None, None),
        ("move_relative", 20.0, 0.0),
        ("pen_down", None, None),
        ("raw_command", None, None),
        ("pen_up", None, None),
        ("move_relative", -20.0, 0.0),
        ("pen_up", None, None),
        ("pen_down", None, None),
        ("raw_command", None, None),
        ("pen_up", None, None),
        ("move_relative", 0.0, 20.0),
        ("pen_down", None, None),
        ("raw_command", None, None),
        ("pen_up", None, None),
        ("move_relative", 0.0, -20.0),
    ]
    assert str(saved_profile.resolve()) in capsys.readouterr().out


def test_remember_model_persists_mapping_by_hardware_id(monkeypatch, tmp_path, capsys) -> None:
    controller = FakeBoundsController()
    config_dir = tmp_path / ".drawcore"

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)
    monkeypatch.setattr(
        cli,
        "discover_devices",
        lambda: [type("Device", (), {"port": "COM4", "description": "USB Serial", "hwid": "USB VID:PID=1A86:8040 SER=01"})()],
    )

    exit_code = cli.main(["remember-model", "--model", "v3a3", "--config-dir", str(config_dir)])

    assert exit_code == 0
    saved = json.loads((config_dir / "devices.json").read_text(encoding="utf-8"))
    assert saved == {"USB VID:PID=1A86:8040 SER=01": "v3a3"}
    output = json.loads(capsys.readouterr().out)
    assert output["model"] == "v3a3"
    assert output["port"] == "COM4"


def test_calibrate_line_width_saves_motion_profile(monkeypatch, tmp_path, capsys) -> None:
    controller = FakeBoundsController()
    answers = iter(["", "0.9", "0.7", "0.5"])
    output_path = tmp_path / "motion.json"
    workspace_path = tmp_path / "workspace.json"
    workspace_path.write_text(
        json.dumps({"model": "default", "width_mm": 100.0, "height_mm": 80.0, "origin_offset_x_mm": 3.0, "origin_offset_y_mm": 4.0}),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    exit_code = cli.main(
        [
            "calibrate-line-width",
            "--output",
            str(output_path),
            "--workspace-config",
            str(workspace_path),
            "--samples",
            "3",
            "--min-feed-rate",
            "400",
            "--max-feed-rate",
            "800",
            "--line-length-mm",
            "12",
            "--line-spacing-mm",
            "5",
            "--offset-x-mm",
            "10",
            "--offset-y-mm",
            "15",
        ]
    )

    assert exit_code == 0
    saved_profile = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved_profile["line_width_calibration"]["fit_kind"] == "piecewise"
    assert saved_profile["line_width_calibration"]["samples"] == [
        {"parameter_value": 400.0, "measured_value": 0.9},
        {"parameter_value": 565.685424949238, "measured_value": 0.7},
        {"parameter_value": 800.0, "measured_value": 0.5},
    ]
    assert controller.calls == [
        ("home", None, None),
        ("pen_up", None, None),
        ("move_relative", 3.0, 4.0),
        ("move_relative", 10.0, 15.0),
        ("pen_down", None, None),
        ("move_relative", 12.0, 0.0),
        ("pen_up", None, None),
        ("move_relative", -12.0, 5.0),
        ("pen_down", None, None),
        ("move_relative", 12.0, 0.0),
        ("pen_up", None, None),
        ("move_relative", -12.0, 5.0),
        ("pen_down", None, None),
        ("move_relative", 12.0, 0.0),
        ("pen_up", None, None),
        ("pen_up", None, None),
        ("move_relative", -10.0, -25.0),
    ]
    assert str(output_path.resolve()) in capsys.readouterr().out


def test_calibrate_blot_size_saves_motion_profile(monkeypatch, tmp_path, capsys) -> None:
    controller = FakeBoundsController()
    answers = iter(["", "0.5", "0.8", "1.1"])
    output_path = tmp_path / "motion.json"
    workspace_path = tmp_path / "workspace.json"
    workspace_path.write_text(
        json.dumps({"model": "default", "width_mm": 100.0, "height_mm": 80.0, "origin_offset_x_mm": 3.0, "origin_offset_y_mm": 4.0}),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    exit_code = cli.main(
        [
            "calibrate-blot-size",
            "--output",
            str(output_path),
            "--workspace-config",
            str(workspace_path),
            "--samples",
            "3",
            "--min-dwell-ms",
            "50",
            "--max-dwell-ms",
            "150",
            "--spot-spacing-mm",
            "5",
            "--offset-x-mm",
            "10",
            "--offset-y-mm",
            "15",
        ]
    )

    assert exit_code == 0
    saved_profile = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved_profile["blot_delay_calibration"]["fit_kind"] == "piecewise"
    assert saved_profile["blot_delay_calibration"]["samples"] == [
        {"parameter_value": 50.0, "measured_value": 0.5},
        {"parameter_value": 86.602540378444, "measured_value": 0.8},
        {"parameter_value": 150.0, "measured_value": 1.1},
    ]
    assert controller.calls == [
        ("home", None, None),
        ("pen_up", None, None),
        ("move_relative", 3.0, 4.0),
        ("move_relative", 10.0, 15.0),
        ("pen_down", None, None),
        ("pen_up", None, None),
        ("move_relative", 0.0, 5.0),
        ("pen_down", None, None),
        ("pen_up", None, None),
        ("move_relative", 0.0, 5.0),
        ("pen_down", None, None),
        ("pen_up", None, None),
        ("pen_up", None, None),
        ("move_relative", -10.0, -25.0),
    ]
    assert str(output_path.resolve()) in capsys.readouterr().out


def test_calibrate_line_width_prompts_for_range_defaults(monkeypatch, tmp_path) -> None:
    controller = FakeBoundsController()
    answers = iter(["", "", "", "0.9", "0.5"])
    output_path = tmp_path / "motion.json"
    workspace_path = tmp_path / "workspace.json"
    workspace_path.write_text(
        json.dumps({"model": "default", "width_mm": 100.0, "height_mm": 80.0, "origin_offset_x_mm": 0.0, "origin_offset_y_mm": 0.0}),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    exit_code = cli.main([
        "calibrate-line-width",
        "--output",
        str(output_path),
        "--workspace-config",
        str(workspace_path),
        "--samples",
        "2",
    ])

    assert exit_code == 0
    saved_profile = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved_profile["line_width_calibration"]["samples"] == [
        {"parameter_value": 25.0, "measured_value": 0.9},
        {"parameter_value": 1200.0, "measured_value": 0.5},
    ]


def test_calibrate_blot_size_prompts_for_long_range_defaults(monkeypatch, tmp_path) -> None:
    controller = FakeBoundsController()
    answers = iter(["", "", "", "0.4", "1.6"])
    output_path = tmp_path / "motion.json"
    workspace_path = tmp_path / "workspace.json"
    workspace_path.write_text(
        json.dumps({"model": "default", "width_mm": 100.0, "height_mm": 80.0, "origin_offset_x_mm": 0.0, "origin_offset_y_mm": 0.0}),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    exit_code = cli.main([
        "calibrate-blot-size",
        "--output",
        str(output_path),
        "--workspace-config",
        str(workspace_path),
        "--samples",
        "2",
    ])

    assert exit_code == 0
    saved_profile = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved_profile["blot_delay_calibration"]["samples"] == [
        {"parameter_value": 100.0, "measured_value": 0.4},
        {"parameter_value": 30000.0, "measured_value": 1.6},
    ]


def test_calibrate_blot_size_uses_host_side_sleep(monkeypatch, tmp_path) -> None:
    controller = FakeBoundsController()
    answers = iter(["", "0.6", "1.2"])
    output_path = tmp_path / "motion.json"
    workspace_path = tmp_path / "workspace.json"
    workspace_path.write_text(
        json.dumps({"model": "default", "width_mm": 100.0, "height_mm": 80.0, "origin_offset_x_mm": 0.0, "origin_offset_y_mm": 0.0}),
        encoding="utf-8",
    )
    sleep_calls: list[float] = []

    monkeypatch.setattr(cli, "_controller_from_args", lambda args: controller)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    exit_code = cli.main([
        "calibrate-blot-size",
        "--output",
        str(output_path),
        "--workspace-config",
        str(workspace_path),
        "--samples",
        "2",
        "--min-dwell-ms",
        "1000",
        "--max-dwell-ms",
        "30000",
    ])

    assert exit_code == 0
    assert sleep_calls == [1.0, 30.0]


def test_calibrate_xy_supports_reverse_half_step_and_bound_clamping(monkeypatch, capsys) -> None:
    controller = FakeBoundsController()
    answers = iter(["h", "b", "25", "", "y", "55.0"])

    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    measured = cli._measure_axis_extent(controller, axis="x", max_extent_mm=25.0, step_mm=20.0)

    assert measured == 55.0
    assert controller.calls == [
        ("pen_up", None, None),
        ("pen_down", None, None),
        ("raw_command", None, None),
        ("pen_up", None, None),
        ("move_relative", 10.0, 0.0),
        ("pen_down", None, None),
        ("raw_command", None, None),
        ("pen_up", None, None),
        ("move_relative", -10.0, 0.0),
        ("pen_down", None, None),
        ("raw_command", None, None),
        ("pen_up", None, None),
        ("move_relative", 25.0, 0.0),
        ("pen_down", None, None),
        ("raw_command", None, None),
        ("pen_up", None, None),
        ("move_relative", -25.0, 0.0),
    ]
    output = capsys.readouterr().out
    assert "Reached the configured X maximum at 25.00 mm." in output