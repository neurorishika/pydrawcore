from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from .controller import DrawCoreController
from .models import MotionConfig


@dataclass(slots=True)
class ProgramError(ValueError):
    message: str
    line_number: int | None = None

    def __str__(self) -> str:
        if self.line_number is None:
            return self.message
        return f"Line {self.line_number}: {self.message}"


@dataclass(slots=True)
class ProgramCommand:
    name: str
    values: tuple[object, ...] = ()
    line_number: int = 0
    source: str = ""
    children: tuple["ProgramCommand", ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "line": self.line_number,
            "command": self.name,
            "values": list(self.values),
            "children": [child.to_dict() for child in self.children],
        }


@dataclass(slots=True)
class Program:
    commands: tuple[ProgramCommand, ...]

    @classmethod
    def from_text(cls, text: str) -> "Program":
        root = _parse_lines(text)
        return cls(commands=tuple(root))

    @classmethod
    def from_file(cls, path: str | Path) -> "Program":
        return cls.from_text(Path(path).read_text(encoding="utf-8"))

    def to_dict(self) -> list[dict[str, object]]:
        return [command.to_dict() for command in self.commands]


@dataclass(slots=True)
class TurtleState:
    x_mm: float = 0.0
    y_mm: float = 0.0
    heading_deg: float = 0.0


@dataclass(slots=True)
class ProgramRunner:
    controller: DrawCoreController
    motion: MotionConfig
    circle_segment_length_mm: float = 1.0
    state: TurtleState = field(default_factory=TurtleState)

    def run(self, program: Program) -> None:
        for command in program.commands:
            self._execute_command(command)

    def _execute_command(self, command: ProgramCommand) -> None:
        if command.name == "HOME":
            self.controller.home()
            self.state.x_mm = 0.0
            self.state.y_mm = 0.0
            return
        if command.name == "PENUP":
            self.controller.pen_up()
            return
        if command.name == "PENDOWN":
            self.controller.pen_down()
            return
        if command.name == "SETHEADING":
            self.state.heading_deg = _normalize_heading(_coerce_float(command.values[0], command))
            return
        if command.name == "LEFT":
            self.state.heading_deg = _normalize_heading(self.state.heading_deg + _coerce_float(command.values[0], command))
            return
        if command.name == "RIGHT":
            self.state.heading_deg = _normalize_heading(self.state.heading_deg - _coerce_float(command.values[0], command))
            return
        if command.name == "MOVE":
            self._move_to(
                _coerce_float(command.values[0], command),
                _coerce_float(command.values[1], command),
            )
            return
        if command.name == "LINE":
            self._draw_line_to(
                _coerce_float(command.values[0], command),
                _coerce_float(command.values[1], command),
                _coerce_optional_float(command.values[2]),
                command,
            )
            return
        if command.name == "FORWARD":
            self._draw_heading_distance(_coerce_float(command.values[0], command), _coerce_optional_float(command.values[1]), command)
            return
        if command.name == "BACK":
            self._draw_heading_distance(-_coerce_float(command.values[0], command), _coerce_optional_float(command.values[1]), command)
            return
        if command.name == "BLOT":
            self._draw_blot(_coerce_float(command.values[0], command), command)
            return
        if command.name == "CIRCLE":
            self._draw_circle(
                _coerce_float(command.values[0], command),
                _coerce_optional_float(command.values[1]),
                command,
            )
            return
        if command.name == "REPEAT":
            repeat_count = _coerce_int(command.values[0], command)
            for _ in range(repeat_count):
                for child in command.children:
                    self._execute_command(child)
            return
        raise ProgramError(f"Unsupported command {command.name}", line_number=command.line_number)

    def _move_to(self, target_x_mm: float, target_y_mm: float) -> None:
        delta_x_mm = target_x_mm - self.state.x_mm
        delta_y_mm = target_y_mm - self.state.y_mm
        self.controller.pen_up()
        self.controller.move_relative(x_mm=delta_x_mm, y_mm=delta_y_mm, feed_rate=self.motion.feed_rate_xy)
        self.state.x_mm = target_x_mm
        self.state.y_mm = target_y_mm

    def _draw_line_to(
        self,
        target_x_mm: float,
        target_y_mm: float,
        line_width_mm: float | None,
        command: ProgramCommand,
    ) -> None:
        delta_x_mm = target_x_mm - self.state.x_mm
        delta_y_mm = target_y_mm - self.state.y_mm
        self._draw_relative(delta_x_mm=delta_x_mm, delta_y_mm=delta_y_mm, line_width_mm=line_width_mm, command=command)

    def _draw_heading_distance(
        self,
        distance_mm: float,
        line_width_mm: float | None,
        command: ProgramCommand,
    ) -> None:
        radians = math.radians(self.state.heading_deg)
        delta_x_mm = math.cos(radians) * distance_mm
        delta_y_mm = math.sin(radians) * distance_mm
        self._draw_relative(delta_x_mm=delta_x_mm, delta_y_mm=delta_y_mm, line_width_mm=line_width_mm, command=command)

    def _draw_relative(
        self,
        *,
        delta_x_mm: float,
        delta_y_mm: float,
        line_width_mm: float | None,
        command: ProgramCommand,
    ) -> None:
        feed_rate = _resolve_line_feed_rate(self.motion, line_width_mm, command)
        self.controller.pen_down()
        self.controller.move_relative(x_mm=delta_x_mm, y_mm=delta_y_mm, feed_rate=feed_rate)
        self.controller.pen_up()
        self.state.x_mm += delta_x_mm
        self.state.y_mm += delta_y_mm

    def _draw_blot(self, blot_size_mm: float, command: ProgramCommand) -> None:
        dwell_ms = _resolve_blot_dwell(self.motion, blot_size_mm, command)
        self.controller.pen_down()
        self.controller.dwell(dwell_ms)
        self.controller.pen_up()

    def _draw_circle(self, diameter_mm: float, line_width_mm: float | None, command: ProgramCommand) -> None:
        if diameter_mm <= 0:
            raise ProgramError("Circle diameter must be greater than zero.", line_number=command.line_number)

        radius_mm = diameter_mm / 2.0
        center_x_mm = self.state.x_mm
        center_y_mm = self.state.y_mm
        circumference_mm = math.pi * diameter_mm
        segment_count = max(12, math.ceil(circumference_mm / max(self.circle_segment_length_mm, 0.25)))
        angle_step = (2.0 * math.pi) / segment_count
        start_x_mm = center_x_mm + radius_mm
        start_y_mm = center_y_mm

        self._move_to(start_x_mm, start_y_mm)
        feed_rate = _resolve_line_feed_rate(self.motion, line_width_mm, command)
        self.controller.pen_down()
        current_x_mm = start_x_mm
        current_y_mm = start_y_mm
        for index in range(1, segment_count + 1):
            angle = angle_step * index
            next_x_mm = center_x_mm + (math.cos(angle) * radius_mm)
            next_y_mm = center_y_mm + (math.sin(angle) * radius_mm)
            self.controller.move_relative(
                x_mm=next_x_mm - current_x_mm,
                y_mm=next_y_mm - current_y_mm,
                feed_rate=feed_rate,
            )
            current_x_mm = next_x_mm
            current_y_mm = next_y_mm
        self.controller.pen_up()
        self.state.x_mm = center_x_mm
        self.state.y_mm = center_y_mm


def parse_program(text: str) -> Program:
    return Program.from_text(text)


def run_program(
    controller: DrawCoreController,
    motion: MotionConfig,
    text: str,
    *,
    start_heading_deg: float = 0.0,
    circle_segment_length_mm: float = 1.0,
) -> Program:
    program = parse_program(text)
    runner = ProgramRunner(
        controller=controller,
        motion=motion,
        circle_segment_length_mm=circle_segment_length_mm,
        state=TurtleState(heading_deg=_normalize_heading(start_heading_deg)),
    )
    runner.run(program)
    return program


def _parse_lines(text: str) -> list[ProgramCommand]:
    root: list[ProgramCommand] = []
    stack: list[list[ProgramCommand]] = [root]
    open_repeat_lines: list[int] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        stripped_line = raw_line.split("#", 1)[0].strip()
        if not stripped_line:
            continue
        tokens = stripped_line.split()
        command_name = tokens[0].upper()

        if command_name == "END":
            if len(stack) == 1:
                raise ProgramError("END without a matching REPEAT block.", line_number=line_number)
            completed_commands = tuple(stack.pop())
            repeat_line = open_repeat_lines.pop()
            repeat_command = stack[-1][-1]
            stack[-1][-1] = ProgramCommand(
                name=repeat_command.name,
                values=repeat_command.values,
                line_number=repeat_line,
                source=repeat_command.source,
                children=completed_commands,
            )
            continue

        command = _parse_command(command_name, tokens[1:], line_number, stripped_line)
        stack[-1].append(command)
        if command_name == "REPEAT":
            stack.append([])
            open_repeat_lines.append(line_number)

    if len(stack) != 1:
        raise ProgramError("REPEAT block is missing a closing END.", line_number=open_repeat_lines[-1])

    return root


def _parse_command(command_name: str, arguments: list[str], line_number: int, source: str) -> ProgramCommand:
    if command_name in {"HOME", "PENUP", "PENDOWN"}:
        _expect_argument_count(command_name, arguments, 0, line_number)
        return ProgramCommand(name=command_name, line_number=line_number, source=source)

    if command_name in {"LEFT", "RIGHT", "SETHEADING", "BLOT"}:
        _expect_argument_count(command_name, arguments, 1, line_number)
        return ProgramCommand(name=command_name, values=(float(arguments[0]),), line_number=line_number, source=source)

    if command_name == "REPEAT":
        _expect_argument_count(command_name, arguments, 1, line_number)
        return ProgramCommand(name=command_name, values=(int(arguments[0]),), line_number=line_number, source=source)

    if command_name == "MOVE":
        _expect_argument_count(command_name, arguments, 2, line_number)
        return ProgramCommand(
            name=command_name,
            values=(float(arguments[0]), float(arguments[1])),
            line_number=line_number,
            source=source,
        )

    if command_name in {"FORWARD", "BACK", "CIRCLE"}:
        return ProgramCommand(
            name=command_name,
            values=_parse_width_arguments(command_name, arguments, line_number),
            line_number=line_number,
            source=source,
        )

    if command_name == "LINE":
        if len(arguments) not in {2, 4}:
            raise ProgramError(
                "LINE expects 'LINE <x_mm> <y_mm>' or 'LINE <x_mm> <y_mm> WIDTH <mm>'.",
                line_number=line_number,
            )
        width_mm: float | None = None
        if len(arguments) == 4:
            if arguments[2].upper() != "WIDTH":
                raise ProgramError("Expected WIDTH keyword before the line width value.", line_number=line_number)
            width_mm = float(arguments[3])
        return ProgramCommand(
            name=command_name,
            values=(float(arguments[0]), float(arguments[1]), width_mm),
            line_number=line_number,
            source=source,
        )

    raise ProgramError(f"Unknown command '{command_name}'.", line_number=line_number)


def _parse_width_arguments(command_name: str, arguments: list[str], line_number: int) -> tuple[object, ...]:
    if len(arguments) not in {1, 3}:
        raise ProgramError(
            f"{command_name} expects '{command_name} <value>' or '{command_name} <value> WIDTH <mm>'.",
            line_number=line_number,
        )
    width_mm: float | None = None
    if len(arguments) == 3:
        if arguments[1].upper() != "WIDTH":
            raise ProgramError("Expected WIDTH keyword before the width value.", line_number=line_number)
        width_mm = float(arguments[2])
    return (float(arguments[0]), width_mm)


def _expect_argument_count(command_name: str, arguments: list[str], count: int, line_number: int) -> None:
    if len(arguments) != count:
        raise ProgramError(
            f"{command_name} expects {count} argument{'s' if count != 1 else ''}.",
            line_number=line_number,
        )


def _resolve_line_feed_rate(
    motion: MotionConfig,
    line_width_mm: float | None,
    command: ProgramCommand,
) -> int:
    if line_width_mm is None:
        return motion.feed_rate_xy
    if line_width_mm <= 0:
        raise ProgramError("Line width must be greater than zero.", line_number=command.line_number)
    calibration = motion.line_width_calibration
    if calibration is None:
        raise ProgramError("Line width commands require a motion profile with line-width calibration.", line_number=command.line_number)
    if calibration.measured_min is not None and line_width_mm < calibration.measured_min:
        raise ProgramError(
            f"Requested line width {line_width_mm:g} mm is below the calibrated minimum of {calibration.measured_min:g} mm.",
            line_number=command.line_number,
        )
    if calibration.measured_max is not None and line_width_mm > calibration.measured_max:
        raise ProgramError(
            f"Requested line width {line_width_mm:g} mm is above the calibrated maximum of {calibration.measured_max:g} mm.",
            line_number=command.line_number,
        )
    feed_rate = motion.feed_rate_for_line_width(line_width_mm)
    if feed_rate is None:
        raise ProgramError("Unable to resolve a feed rate for the requested line width.", line_number=command.line_number)
    return feed_rate


def _resolve_blot_dwell(
    motion: MotionConfig,
    blot_size_mm: float,
    command: ProgramCommand,
) -> int:
    if blot_size_mm <= 0:
        raise ProgramError("Blot size must be greater than zero.", line_number=command.line_number)
    calibration = motion.blot_delay_calibration
    if calibration is None:
        raise ProgramError("BLOT commands require a motion profile with blot-size calibration.", line_number=command.line_number)
    if calibration.measured_min is not None and blot_size_mm < calibration.measured_min:
        raise ProgramError(
            f"Requested blot size {blot_size_mm:g} mm is below the calibrated minimum of {calibration.measured_min:g} mm.",
            line_number=command.line_number,
        )
    if calibration.measured_max is not None and blot_size_mm > calibration.measured_max:
        raise ProgramError(
            f"Requested blot size {blot_size_mm:g} mm is above the calibrated maximum of {calibration.measured_max:g} mm.",
            line_number=command.line_number,
        )
    dwell_ms = motion.blot_delay_for_size(blot_size_mm)
    if dwell_ms is None:
        raise ProgramError("Unable to resolve a dwell time for the requested blot size.", line_number=command.line_number)
    return dwell_ms


def _coerce_float(value: object, command: ProgramCommand) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ProgramError("Expected a numeric value.", line_number=command.line_number) from exc


def _coerce_optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _coerce_int(value: object, command: ProgramCommand) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ProgramError("Expected an integer value.", line_number=command.line_number) from exc


def _normalize_heading(value: float) -> float:
    return value % 360.0