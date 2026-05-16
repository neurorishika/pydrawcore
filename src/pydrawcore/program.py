"""Parser, preview, and execution engine for the turtle-style drawing DSL."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from .controller import DrawCoreController
from .models import MotionConfig, WorkspaceBounds


@dataclass(slots=True)
class ProgramError(ValueError):
    """Raised when parsing or executing a drawing program fails."""

    message: str
    line_number: int | None = None

    def __str__(self) -> str:
        if self.line_number is None:
            return self.message
        return f"Line {self.line_number}: {self.message}"


@dataclass(slots=True)
class ProgramCommand:
    """Normalized representation of a parsed DSL command."""

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
    """Parsed turtle program represented as a top-level command list."""

    commands: tuple[ProgramCommand, ...]

    @classmethod
    def from_text(cls, text: str) -> "Program":
        """Parse a program directly from raw text content."""
        root = _parse_lines(text)
        return cls(commands=tuple(root))

    @classmethod
    def from_file(cls, path: str | Path) -> "Program":
        """Read and parse a program file from disk."""
        return cls.from_text(Path(path).read_text(encoding="utf-8"))

    def to_dict(self) -> list[dict[str, object]]:
        return [command.to_dict() for command in self.commands]


@dataclass(slots=True)
class TurtleState:
    """Mutable runner state for current position and heading."""

    x_mm: float = 0.0
    y_mm: float = 0.0
    heading_deg: float = 0.0
    default_line_width_mm: float | None = None


@dataclass(slots=True)
class PreviewOperation:
    """Single previewable machine action emitted by a turtle program."""

    kind: str
    start_x_mm: float | None = None
    start_y_mm: float | None = None
    end_x_mm: float | None = None
    end_y_mm: float | None = None
    feed_rate: int | None = None
    estimated_width_mm: float | None = None
    dwell_ms: float | None = None
    estimated_blot_size_mm: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "start_x_mm": self.start_x_mm,
            "start_y_mm": self.start_y_mm,
            "end_x_mm": self.end_x_mm,
            "end_y_mm": self.end_y_mm,
            "feed_rate": self.feed_rate,
            "estimated_width_mm": self.estimated_width_mm,
            "dwell_ms": self.dwell_ms,
            "estimated_blot_size_mm": self.estimated_blot_size_mm,
        }


@dataclass(slots=True)
class ProgramPreview:
    """Previewable representation of the compiled turtle motion plan."""

    operations: tuple[PreviewOperation, ...]

    def bounds(self) -> tuple[float, float, float, float]:
        x_values = [0.0]
        y_values = [0.0]
        for operation in self.operations:
            for value in (operation.start_x_mm, operation.end_x_mm):
                if value is not None:
                    x_values.append(value)
            for value in (operation.start_y_mm, operation.end_y_mm):
                if value is not None:
                    y_values.append(value)
        return min(x_values), max(x_values), min(y_values), max(y_values)

    def to_dict(self) -> dict[str, object]:
        min_x_mm, max_x_mm, min_y_mm, max_y_mm = self.bounds()
        return {
            "bounds": {
                "min_x_mm": min_x_mm,
                "max_x_mm": max_x_mm,
                "min_y_mm": min_y_mm,
                "max_y_mm": max_y_mm,
            },
            "operations": [operation.to_dict() for operation in self.operations],
        }


@dataclass(slots=True)
class PreviewController:
    """Controller-like sink that records travel, draw, and blot operations."""

    motion: MotionConfig
    x_mm: float = 0.0
    y_mm: float = 0.0
    pen_is_down: bool = False
    operations: list[PreviewOperation] = field(default_factory=list)

    def pen_up(self) -> None:
        self.pen_is_down = False

    def pen_down(self) -> None:
        self.pen_is_down = True

    def move_relative(self, *, x_mm: float = 0.0, y_mm: float = 0.0, feed_rate=None) -> None:
        next_x_mm = self.x_mm + x_mm
        next_y_mm = self.y_mm + y_mm
        operation_kind = "draw" if self.pen_is_down else "travel"
        estimated_width_mm = None
        if operation_kind == "draw" and feed_rate is not None and self.motion.line_width_calibration is not None:
            estimated_width_mm = self.motion.line_width_calibration.predict_measured_value(float(feed_rate))
        self.operations.append(
            PreviewOperation(
                kind=operation_kind,
                start_x_mm=self.x_mm,
                start_y_mm=self.y_mm,
                end_x_mm=next_x_mm,
                end_y_mm=next_y_mm,
                feed_rate=feed_rate,
                estimated_width_mm=estimated_width_mm,
            )
        )
        self.x_mm = next_x_mm
        self.y_mm = next_y_mm

    def move_absolute(self, *, x_mm: float = 0.0, y_mm: float = 0.0, feed_rate=None) -> None:
        if x_mm == self.x_mm and y_mm == self.y_mm:
            return
        operation_kind = "draw" if self.pen_is_down else "travel"
        estimated_width_mm = None
        if operation_kind == "draw" and feed_rate is not None and self.motion.line_width_calibration is not None:
            estimated_width_mm = self.motion.line_width_calibration.predict_measured_value(float(feed_rate))
        self.operations.append(
            PreviewOperation(
                kind=operation_kind,
                start_x_mm=self.x_mm,
                start_y_mm=self.y_mm,
                end_x_mm=x_mm,
                end_y_mm=y_mm,
                feed_rate=feed_rate,
                estimated_width_mm=estimated_width_mm,
            )
        )
        self.x_mm = x_mm
        self.y_mm = y_mm

    def dwell(self, milliseconds: int | float) -> None:
        estimated_blot_size_mm = None
        if self.motion.blot_delay_calibration is not None:
            estimated_blot_size_mm = self.motion.blot_delay_calibration.predict_measured_value(float(milliseconds))
        self.operations.append(
            PreviewOperation(
                kind="blot",
                start_x_mm=self.x_mm,
                start_y_mm=self.y_mm,
                end_x_mm=self.x_mm,
                end_y_mm=self.y_mm,
                dwell_ms=float(milliseconds),
                estimated_blot_size_mm=estimated_blot_size_mm,
            )
        )

    def home(self) -> None:
        if self.x_mm != 0.0 or self.y_mm != 0.0:
            self.operations.append(
                PreviewOperation(
                    kind="home",
                    start_x_mm=self.x_mm,
                    start_y_mm=self.y_mm,
                    end_x_mm=0.0,
                    end_y_mm=0.0,
                )
            )
        self.pen_is_down = False
        self.x_mm = 0.0
        self.y_mm = 0.0


@dataclass(slots=True)
class ProgramRunner:
    """Execute parsed turtle programs against a connected controller."""

    controller: DrawCoreController
    motion: MotionConfig
    circle_segment_length_mm: float = 1.0
    plot_origin_x_mm: float = 0.0
    plot_origin_y_mm: float = 0.0
    state: TurtleState = field(default_factory=TurtleState)

    def run(
        self,
        program: Program,
        *,
        move_to_origin_before: bool = True,
        move_to_origin_after: bool = True,
    ) -> None:
        """Execute each top-level command in order.

        The pen is raised and the machine is commanded to the calibrated
        plotting origin unconditionally both before the first command and
        after the last, so every run starts and ends at a verified known
        position regardless of what the state tracker contains.
        """
        if move_to_origin_before:
            # Always issue the absolute move — never rely on the state tracker
            # already being at (0, 0), because the machine may not be.
            self.controller.pen_up()
            self._move_machine_absolute(x_mm=0.0, y_mm=0.0, feed_rate=self.motion.feed_rate_travel)
            self.state.x_mm = 0.0
            self.state.y_mm = 0.0
        for command in program.commands:
            self._execute_command(command)
        if move_to_origin_after:
            self.controller.pen_up()
            self._move_machine_absolute(x_mm=0.0, y_mm=0.0, feed_rate=self.motion.feed_rate_travel)
            self.state.x_mm = 0.0
            self.state.y_mm = 0.0

    def _move_machine_absolute(self, *, x_mm: float, y_mm: float, feed_rate: int) -> None:
        self.controller.move_absolute(
            x_mm=self.plot_origin_x_mm + x_mm,
            y_mm=self.plot_origin_y_mm + y_mm,
            feed_rate=feed_rate,
        )

    def return_to_origin(self) -> None:
        """Travel back to the program origin with the pen raised."""
        self._move_to(0.0, 0.0)

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
        if command.name == "SETWIDTH":
            self.state.default_line_width_mm = _coerce_width_setting(command.values[0], command)
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
        if target_x_mm == self.state.x_mm and target_y_mm == self.state.y_mm:
            return
        self.controller.pen_up()
        self._move_machine_absolute(x_mm=target_x_mm, y_mm=target_y_mm, feed_rate=self.motion.feed_rate_travel)
        self.state.x_mm = target_x_mm
        self.state.y_mm = target_y_mm

    def _draw_line_to(
        self,
        target_x_mm: float,
        target_y_mm: float,
        line_width_mm: float | None,
        command: ProgramCommand,
    ) -> None:
        # LINE has an explicit absolute target — use it directly rather than
        # converting to a delta and back, which would discard the exact
        # parsed coordinates through floating-point round-trip error.
        feed_rate = _resolve_line_feed_rate(self.motion, self._effective_line_width(line_width_mm), command)
        self.controller.pen_down()
        self._move_machine_absolute(x_mm=target_x_mm, y_mm=target_y_mm, feed_rate=feed_rate)
        self.controller.pen_up()
        self.state.x_mm = target_x_mm
        self.state.y_mm = target_y_mm

    def _draw_heading_distance(
        self,
        distance_mm: float,
        line_width_mm: float | None,
        command: ProgramCommand,
    ) -> None:
        radians = math.radians(self.state.heading_deg)
        delta_x_mm = math.cos(radians) * distance_mm
        delta_y_mm = math.sin(radians) * distance_mm
        self._draw_relative(
            delta_x_mm=delta_x_mm,
            delta_y_mm=delta_y_mm,
            line_width_mm=self._effective_line_width(line_width_mm),
            command=command,
        )

    def _effective_line_width(self, line_width_mm: float | None) -> float | None:
        if line_width_mm is not None:
            return line_width_mm
        return self.state.default_line_width_mm

    def _draw_relative(
        self,
        *,
        delta_x_mm: float,
        delta_y_mm: float,
        line_width_mm: float | None,
        command: ProgramCommand,
    ) -> None:
        feed_rate = _resolve_line_feed_rate(self.motion, line_width_mm, command)
        target_x_mm = self.state.x_mm + delta_x_mm
        target_y_mm = self.state.y_mm + delta_y_mm
        self.controller.pen_down()
        self._move_machine_absolute(x_mm=target_x_mm, y_mm=target_y_mm, feed_rate=feed_rate)
        self.controller.pen_up()
        self.state.x_mm = target_x_mm
        self.state.y_mm = target_y_mm

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
        effective_line_width_mm = self._effective_line_width(line_width_mm)

        self._move_to(start_x_mm, start_y_mm)
        feed_rate = _resolve_line_feed_rate(self.motion, effective_line_width_mm, command)
        self.controller.pen_down()
        next_x_mm = start_x_mm
        next_y_mm = start_y_mm
        for index in range(1, segment_count + 1):
            angle = angle_step * index
            next_x_mm = center_x_mm + (math.cos(angle) * radius_mm)
            next_y_mm = center_y_mm + (math.sin(angle) * radius_mm)
            self._move_machine_absolute(x_mm=next_x_mm, y_mm=next_y_mm, feed_rate=feed_rate)
        self.controller.pen_up()
        # Update state to the actual machine position (arc end ≈ arc start),
        # then travel back to the circle centre so the turtle's logical
        # position matches the machine position before the next command.
        self.state.x_mm = next_x_mm
        self.state.y_mm = next_y_mm
        self._move_to(center_x_mm, center_y_mm)


def parse_program(text: str) -> Program:
    """Parse raw turtle DSL text into a :class:`Program`."""
    return Program.from_text(text)


def check_program_fits_workspace(
    motion: MotionConfig,
    text: str,
    workspace_bounds: WorkspaceBounds,
    *,
    start_heading_deg: float = 0.0,
    circle_segment_length_mm: float = 1.0,
) -> None:
    """Run a preview and raise :class:`ProgramError` if any motion falls outside the workspace.

    The plottable area is ``[0, workspace_bounds.width_mm]`` × ``[0, workspace_bounds.height_mm]``.
    All travel *and* draw moves are checked; exceeding any edge is rejected before hardware moves.
    """
    preview = preview_program(
        motion,
        text,
        start_heading_deg=start_heading_deg,
        circle_segment_length_mm=circle_segment_length_mm,
    )
    min_x_mm, max_x_mm, min_y_mm, max_y_mm = preview.bounds()
    violations: list[str] = []
    if min_x_mm < 0.0:
        violations.append(f"left edge at {min_x_mm:.2f} mm (minimum 0.00 mm)")
    if min_y_mm < 0.0:
        violations.append(f"bottom edge at {min_y_mm:.2f} mm (minimum 0.00 mm)")
    if max_x_mm > workspace_bounds.width_mm:
        violations.append(
            f"right edge at {max_x_mm:.2f} mm (maximum {workspace_bounds.width_mm:.2f} mm)"
        )
    if max_y_mm > workspace_bounds.height_mm:
        violations.append(
            f"top edge at {max_y_mm:.2f} mm (maximum {workspace_bounds.height_mm:.2f} mm)"
        )
    if violations:
        raise ProgramError(
            "Program exceeds plottable workspace: " + "; ".join(violations)
        )


def run_program(
    controller: DrawCoreController,
    motion: MotionConfig,
    text: str,
    *,
    start_heading_deg: float = 0.0,
    circle_segment_length_mm: float = 1.0,
    workspace_bounds: WorkspaceBounds | None = None,
) -> Program:
    """Parse and execute a turtle program using the supplied controller.

    If *workspace_bounds* is provided the program is previewed first and a
    :class:`ProgramError` is raised when any move would fall outside the
    plottable area, preventing any hardware motion.
    """
    if workspace_bounds is not None:
        check_program_fits_workspace(
            motion,
            text,
            workspace_bounds,
            start_heading_deg=start_heading_deg,
            circle_segment_length_mm=circle_segment_length_mm,
        )
    program = parse_program(text)
    runner = ProgramRunner(
        controller=controller,
        motion=motion,
        circle_segment_length_mm=circle_segment_length_mm,
        plot_origin_x_mm=(workspace_bounds.origin_offset_x_mm if workspace_bounds is not None else 0.0),
        plot_origin_y_mm=(workspace_bounds.origin_offset_y_mm if workspace_bounds is not None else 0.0),
        state=TurtleState(heading_deg=_normalize_heading(start_heading_deg)),
    )
    runner.run(program)
    return program


def preview_program(
    motion: MotionConfig,
    text: str,
    *,
    start_heading_deg: float = 0.0,
    circle_segment_length_mm: float = 1.0,
    return_to_origin: bool = False,
) -> ProgramPreview:
    """Parse a turtle program and record the resulting motion plan without hardware."""
    program = parse_program(text)
    controller = PreviewController(motion=motion)
    runner = ProgramRunner(
        controller=controller,
        motion=motion,
        circle_segment_length_mm=circle_segment_length_mm,
        state=TurtleState(heading_deg=_normalize_heading(start_heading_deg)),
    )
    controller.pen_up()
    runner.run(program)
    if return_to_origin:
        controller.pen_up()
        runner.return_to_origin()
    return ProgramPreview(operations=tuple(controller.operations))


def export_preview_svg(
    preview: ProgramPreview,
    output_path: str | Path,
    *,
    workspace_bounds: WorkspaceBounds | None = None,
) -> Path:
    """Render a previewed turtle plan to an SVG file."""
    margin_mm = 10.0
    min_x_mm, max_x_mm, min_y_mm, max_y_mm = preview.bounds()
    if workspace_bounds is not None:
        min_x_mm = min(min_x_mm, 0.0)
        min_y_mm = min(min_y_mm, 0.0)
        max_x_mm = max(max_x_mm, workspace_bounds.width_mm)
        max_y_mm = max(max_y_mm, workspace_bounds.height_mm)

    canvas_width_mm = (max_x_mm - min_x_mm) + (2 * margin_mm)
    canvas_height_mm = (max_y_mm - min_y_mm) + (2 * margin_mm)

    def svg_x(x_mm: float) -> float:
        return (x_mm - min_x_mm) + margin_mm

    def svg_y(y_mm: float) -> float:
        return (max_y_mm - y_mm) + margin_mm

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_width_mm:.2f}mm" height="{canvas_height_mm:.2f}mm" viewBox="0 0 {canvas_width_mm:.2f} {canvas_height_mm:.2f}">',
        '<rect width="100%" height="100%" fill="#fffdf7"/>',
    ]

    if workspace_bounds is not None:
        lines.append(
            f'<rect x="{svg_x(0.0):.2f}" y="{svg_y(workspace_bounds.height_mm):.2f}" width="{workspace_bounds.width_mm:.2f}" height="{workspace_bounds.height_mm:.2f}" fill="none" stroke="#d7d0c4" stroke-width="0.35"/>'
        )

    origin_x = svg_x(0.0)
    origin_y = svg_y(0.0)
    lines.extend(
        [
            f'<line x1="{origin_x - 2:.2f}" y1="{origin_y:.2f}" x2="{origin_x + 2:.2f}" y2="{origin_y:.2f}" stroke="#b35c37" stroke-width="0.4"/>',
            f'<line x1="{origin_x:.2f}" y1="{origin_y - 2:.2f}" x2="{origin_x:.2f}" y2="{origin_y + 2:.2f}" stroke="#b35c37" stroke-width="0.4"/>',
        ]
    )

    for operation in preview.operations:
        if operation.kind in {"travel", "draw", "home"} and operation.start_x_mm is not None and operation.end_x_mm is not None:
            stroke = "#c8c2b8" if operation.kind != "draw" else "#141414"
            dash = ' stroke-dasharray="2 2"' if operation.kind != "draw" else ""
            stroke_width = operation.estimated_width_mm if operation.estimated_width_mm is not None else (0.3 if operation.kind == "draw" else 0.2)
            lines.append(
                f'<line x1="{svg_x(operation.start_x_mm):.2f}" y1="{svg_y(operation.start_y_mm or 0.0):.2f}" x2="{svg_x(operation.end_x_mm):.2f}" y2="{svg_y(operation.end_y_mm or 0.0):.2f}" stroke="{stroke}" stroke-width="{stroke_width:.2f}" stroke-linecap="round"{dash}/>'
            )
        elif operation.kind == "blot" and operation.start_x_mm is not None and operation.start_y_mm is not None:
            radius_mm = (operation.estimated_blot_size_mm or 0.5) / 2.0
            lines.append(
                f'<circle cx="{svg_x(operation.start_x_mm):.2f}" cy="{svg_y(operation.start_y_mm):.2f}" r="{radius_mm:.2f}" fill="#141414"/>'
            )

    lines.append("</svg>")
    resolved_path = Path(output_path).expanduser().resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return resolved_path


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

    if command_name == "SETWIDTH":
        _expect_argument_count(command_name, arguments, 1, line_number)
        return ProgramCommand(name=command_name, values=(_parse_width_setting(arguments[0]),), line_number=line_number, source=source)

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


def _parse_width_setting(argument: str) -> float | None:
    normalized = argument.strip().upper()
    if normalized in {"NONE", "OFF", "DEFAULT"}:
        return None
    return float(argument)


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


def _coerce_width_setting(value: object, command: ProgramCommand) -> float | None:
    if value is None:
        return None
    width_mm = _coerce_float(value, command)
    if width_mm <= 0:
        raise ProgramError("SETWIDTH requires a width greater than zero.", line_number=command.line_number)
    return width_mm


def _coerce_int(value: object, command: ProgramCommand) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ProgramError("Expected an integer value.", line_number=command.line_number) from exc


def _normalize_heading(value: float) -> float:
    return value % 360.0