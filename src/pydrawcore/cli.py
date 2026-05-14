from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from .controller import DrawCoreController
from .discovery import discover_devices
from .models import (
    CalibrationModel,
    CalibrationSample,
    DRAWCORE_WORKSPACE_PRESETS,
    DiscoveredDevice,
    MotionConfig,
    PEN_POSITION_MAX,
    PEN_POSITION_MIN,
    WorkspaceBounds,
    clamp_pen_position,
    workspace_bounds_for_model,
)
from .paths import (
    default_device_model_map_path,
    default_motion_profile_path,
    default_workspace_profile_path,
    ensure_config_dir,
)
from .program import ProgramError, ProgramRunner, TurtleState, check_program_fits_workspace, export_preview_svg, parse_program, preview_program


def _add_port_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--port", help="Serial port, for example COM4")


def _add_motion_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--motion-config",
        help="Path to a JSON motion profile with feed rates and pen positions",
    )


def _add_workspace_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace-config",
        help="Path to a JSON workspace profile with calibrated width and height",
    )


def _add_config_dir_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config-dir",
        help="Directory for persisted pydrawcore profiles; defaults to ~/.drawcore",
    )


def _default_motion_profile_path(args: argparse.Namespace) -> Path:
    return default_motion_profile_path(getattr(args, "config_dir", None))


def _default_workspace_profile_path(args: argparse.Namespace) -> Path:
    return default_workspace_profile_path(getattr(args, "config_dir", None))


def _default_device_model_map_path(args: argparse.Namespace) -> Path:
    return default_device_model_map_path(getattr(args, "config_dir", None))


def _motion_from_args(args: argparse.Namespace) -> MotionConfig | None:
    motion_config_path = getattr(args, "motion_config", None)
    if motion_config_path:
        return MotionConfig.from_file(motion_config_path)

    default_profile = _default_motion_profile_path(args)
    if default_profile.exists():
        return MotionConfig.from_file(default_profile)
    return None


def _save_motion_profile(args: argparse.Namespace, motion: MotionConfig) -> Path:
    output = getattr(args, "output", None)
    if output:
        output_path = Path(output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        ensure_config_dir(getattr(args, "config_dir", None))
        output_path = _default_motion_profile_path(args)
    motion.to_file(output_path)
    return output_path


def _workspace_from_args(args: argparse.Namespace) -> WorkspaceBounds | None:
    workspace_config_path = getattr(args, "workspace_config", None)
    if workspace_config_path:
        workspace_path = Path(workspace_config_path).expanduser().resolve()
        if workspace_path.exists():
            return WorkspaceBounds.from_file(workspace_path)
        return None

    default_profile = _default_workspace_profile_path(args)
    if default_profile.exists() and not getattr(args, "use_model_preset", False):
        return WorkspaceBounds.from_file(default_profile)
    return None


def _save_workspace_profile(
    args: argparse.Namespace,
    bounds: WorkspaceBounds,
    *,
    use_output_path: bool = True,
) -> Path:
    output = getattr(args, "output", None)
    if use_output_path and output:
        output_path = Path(output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
    elif getattr(args, "workspace_config", None):
        output_path = Path(args.workspace_config).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        ensure_config_dir(getattr(args, "config_dir", None))
        output_path = _default_workspace_profile_path(args)
    bounds.to_file(output_path)
    return output_path


def _load_device_model_map(args: argparse.Namespace) -> dict[str, str]:
    path = _default_device_model_map_path(args)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_device_model_map(args: argparse.Namespace, model_map: dict[str, str]) -> Path:
    ensure_config_dir(getattr(args, "config_dir", None))
    output_path = _default_device_model_map_path(args)
    output_path.write_text(json.dumps(model_map, indent=2) + "\n", encoding="utf-8")
    return output_path


def _find_connected_device(port_name: str | None) -> DiscoveredDevice | None:
    devices = discover_devices()
    if port_name is not None:
        for device in devices:
            if device.port == port_name:
                return device
        return None
    if len(devices) == 1:
        return devices[0]
    return None


def _remembered_model_for_device(args: argparse.Namespace, device: DiscoveredDevice | None) -> str | None:
    if device is None:
        return None
    return _load_device_model_map(args).get(device.hwid)


def _resolve_workspace_bounds(args: argparse.Namespace) -> WorkspaceBounds:
    saved_bounds = _workspace_from_args(args)
    if (
        saved_bounds is not None
        and args.model is None
        and args.width_mm is None
        and args.height_mm is None
    ):
        return saved_bounds

    selected_model = _select_workspace_model(args)
    bounds = workspace_bounds_for_model(selected_model)
    width_mm = args.width_mm if args.width_mm is not None else bounds.width_mm
    height_mm = args.height_mm if args.height_mm is not None else bounds.height_mm
    return WorkspaceBounds(
        model=bounds.model,
        width_mm=width_mm,
        height_mm=height_mm,
        origin_offset_x_mm=(saved_bounds.origin_offset_x_mm if saved_bounds is not None else bounds.origin_offset_x_mm),
        origin_offset_y_mm=(saved_bounds.origin_offset_y_mm if saved_bounds is not None else bounds.origin_offset_y_mm),
    )


def _require_workspace_profile(args: argparse.Namespace) -> WorkspaceBounds:
    bounds = _workspace_from_args(args)
    if bounds is None:
        raise ValueError(
            "A saved workspace profile with the plotting-origin offset is required. Run calibrate-pen first."
        )
    return bounds


def _move_to_plot_origin(controller: DrawCoreController, bounds: WorkspaceBounds) -> None:
    if bounds.origin_offset_x_mm == 0.0 and bounds.origin_offset_y_mm == 0.0:
        return
    controller.move_absolute(x_mm=bounds.origin_offset_x_mm, y_mm=bounds.origin_offset_y_mm)


def _seed_workspace_bounds_for_controller(
    args: argparse.Namespace,
    controller: DrawCoreController,
) -> WorkspaceBounds:
    saved_bounds = _workspace_from_args(args)
    if saved_bounds is not None:
        return saved_bounds

    explicit_model = getattr(args, "model", None)
    if explicit_model is not None:
        return workspace_bounds_for_model(explicit_model)

    device = _find_connected_device(getattr(controller, "port_name", None))
    remembered_model = _remembered_model_for_device(args, device)
    if remembered_model is not None:
        return workspace_bounds_for_model(remembered_model)

    get_inferred_model = getattr(controller, "get_inferred_model", None)
    inferred_model = get_inferred_model() if callable(get_inferred_model) else None
    if inferred_model is not None:
        return workspace_bounds_for_model(inferred_model)

    return workspace_bounds_for_model("default")


def _select_workspace_model(args: argparse.Namespace) -> str:
    if args.model is not None:
        return args.model
    if not getattr(args, "use_model_preset", False):
        return "default"

    with _controller_from_args(args) as controller:
        device = _find_connected_device(controller.port_name)
        remembered_model = _remembered_model_for_device(args, device)
        if remembered_model is not None:
            return remembered_model
        inferred_model = controller.get_inferred_model()
    return inferred_model or "default"


def _mark_workspace_bounds(args: argparse.Namespace, bounds: WorkspaceBounds) -> None:
    inset_mm = max(args.inset_mm, 0.0)
    drawable_width_mm = bounds.width_mm - (2 * inset_mm)
    drawable_height_mm = bounds.height_mm - (2 * inset_mm)
    if drawable_width_mm <= 0 or drawable_height_mm <= 0:
        raise ValueError("Inset is larger than the selected workspace bounds.")

    with _controller_from_args(args) as controller:
        if not args.skip_home:
            plot_origin = _require_workspace_profile(args)
            controller.home()
        controller.pen_up()
        if not args.skip_home:
            _move_to_plot_origin(controller, plot_origin)
        if inset_mm:
            controller.move_relative(x_mm=inset_mm, y_mm=inset_mm)
        controller.pen_down()
        controller.move_relative(x_mm=drawable_width_mm)
        controller.move_relative(y_mm=drawable_height_mm)
        controller.move_relative(x_mm=-drawable_width_mm)
        controller.move_relative(y_mm=-drawable_height_mm)
        controller.pen_up()


def _measure_axis_extent(
    controller: DrawCoreController,
    *,
    axis: str,
    max_extent_mm: float,
    step_mm: float,
    plot_origin_bounds: WorkspaceBounds,
) -> float:
    traveled_mm = 0.0
    controller.pen_up()
    _mark_calibration_point(controller)
    print(
        f"{axis.upper()} calibration: press Enter to move +{step_mm:g} mm, type h for +{step_mm / 2:g} mm, "
        f"b for -{step_mm:g} mm, bh for -{step_mm / 2:g} mm, enter a signed mm delta for a custom move, "
        "type y when you want to stop and measure, or q to quit. Each stop marks a point with pen-down, then raises before moving again." \
        "Press r to reset back to the origin if you want to start over."
    )

    while True:
        print(f"Enter for +{step_mm:g} mm, h for +{step_mm / 2:g} mm, b for -{step_mm:g} mm, bh for -{step_mm / 2:g} mm, or a signed mm delta.")
        response = input(f"{axis.upper()} distance {traveled_mm:.2f} mm. Accept? (y)es/(r)eset/(q)uit or other input: ").strip().lower()
        if response == "y":
            break
        if response == "q":
            raise KeyboardInterrupt("Calibration cancelled by user.")
        if response == "r":
            # move to plot origin and reset traveled distance
            _move_to_plot_origin(controller, plot_origin_bounds)
            traveled_mm = 0.0
            _mark_calibration_point(controller)
            continue

        try:
            requested_delta_mm = _parse_axis_calibration_delta(response, step_mm)
        except ValueError:
            print("Invalid response. Use Enter, h, b, bh, y, q, r, or a signed millimeter delta.")
            continue

        next_extent_mm = min(max(traveled_mm + requested_delta_mm, 0.0), max_extent_mm)
        delta_mm = next_extent_mm - traveled_mm
        if delta_mm == 0:
            if requested_delta_mm > 0:
                print(f"Reached the configured {axis.upper()} maximum at {max_extent_mm:.2f} mm.")
            elif requested_delta_mm < 0:
                print(f"Already back at the plotting origin for {axis.upper()} calibration.")
            continue
        if axis == "x":
            controller.move_relative(x_mm=delta_mm)
        else:
            controller.move_relative(y_mm=delta_mm)
        traveled_mm = next_extent_mm
        _mark_calibration_point(controller)

    measured_mm = float(input(f"Enter the measured physical {axis.upper()} distance in mm: ").strip())
    if axis == "x":
        controller.move_relative(x_mm=-traveled_mm)
    else:
        controller.move_relative(y_mm=-traveled_mm)
    return measured_mm


def _mark_calibration_point(controller: DrawCoreController) -> None:
    controller.pen_down()
    controller.raw_command("G4 P0.15")
    controller.pen_up()


def _parse_axis_calibration_delta(response: str, step_mm: float) -> float:
    if response == "":
        return step_mm
    if response == "h":
        return step_mm / 2.0
    if response == "b":
        return -step_mm
    if response in {"bh", "hb"}:
        return -(step_mm / 2.0)
    return float(response)


def _build_calibrated_workspace_bounds(args: argparse.Namespace) -> WorkspaceBounds:
    preset_bounds = workspace_bounds_for_model(args.model)
    plot_origin_bounds = _require_workspace_profile(args)
    max_x_mm = args.max_x_mm if args.max_x_mm is not None else preset_bounds.width_mm
    max_y_mm = args.max_y_mm if args.max_y_mm is not None else preset_bounds.height_mm
    step_mm = max(args.step_mm, 1.0)

    with _controller_from_args(args) as controller:
        controller.home()
        controller.pen_up()
        _move_to_plot_origin(controller, plot_origin_bounds)
        _prompt_ready(
            "Homing complete. Verify the pen is over the saved plotting origin, then press Enter to start X calibration or q to quit: "
        )
        measured_x_mm = _measure_axis_extent(
            controller,
            axis="x",
            max_extent_mm=max_x_mm,
            step_mm=step_mm,
            plot_origin_bounds=plot_origin_bounds,
        )
        _prompt_ready(
            "Return the rig to the saved plotting origin before Y calibration, then press Enter to continue or q to quit: "
        )
        measured_y_mm = _measure_axis_extent(
            controller,
            axis="y",
            max_extent_mm=max_y_mm,
            step_mm=step_mm,
            plot_origin_bounds=plot_origin_bounds,
        )

    return WorkspaceBounds(
        model=args.model,
        width_mm=measured_x_mm,
        height_mm=measured_y_mm,
        origin_offset_x_mm=plot_origin_bounds.origin_offset_x_mm,
        origin_offset_y_mm=plot_origin_bounds.origin_offset_y_mm,
    )


def _controller_from_args(args: argparse.Namespace) -> DrawCoreController:
    motion = _motion_from_args(args)
    if args.port:
        return DrawCoreController.connect(args.port, motion=motion)
    return DrawCoreController.auto_connect(motion=motion)


def _prompt_ready(message: str) -> None:
    response = input(message).strip().lower()
    if response == "q":
        raise KeyboardInterrupt("Calibration cancelled by user.")


def _prompt_measured_value(message: str) -> float:
    while True:
        response = input(message).strip().lower()
        if response == "q":
            raise KeyboardInterrupt("Calibration cancelled by user.")
        try:
            return float(response)
        except ValueError:
            print("Enter a numeric measurement in millimeters or q to quit.")


def _prompt_float_with_default(message: str, *, default: float, minimum: float | None = None) -> float:
    while True:
        response = input(f"{message} [{default:g}] ").strip().lower()
        if response == "q":
            raise KeyboardInterrupt("Calibration cancelled by user.")
        if response == "":
            value = default
        else:
            try:
                value = float(response)
            except ValueError:
                print("Enter a numeric value or q to quit.")
                continue
        if minimum is not None and value < minimum:
            print(f"Enter a value greater than or equal to {minimum:g}.")
            continue
        return value


def _build_sample_values(minimum: float, maximum: float, count: int) -> list[float]:
    if count < 2:
        raise ValueError("Calibration requires at least two samples.")
    if minimum <= 0:
        raise ValueError("Calibration minimum must be greater than zero for logarithmic sampling.")
    if maximum <= minimum:
        raise ValueError("Calibration maximum must be greater than the minimum.")
    if count == 2:
        return [minimum, maximum]
    log_minimum = math.log(minimum)
    log_maximum = math.log(maximum)
    log_step = (log_maximum - log_minimum) / (count - 1)
    values = [round(math.exp(log_minimum + (index * log_step)), 12) for index in range(count)]
    values[0] = minimum
    values[-1] = maximum
    return values


def _motion_with_calibration(
    motion: MotionConfig,
    *,
    line_width_calibration: CalibrationModel | None = None,
    blot_delay_calibration: CalibrationModel | None = None,
) -> MotionConfig:
    return MotionConfig(
        feed_rate_xy=motion.feed_rate_xy,
        feed_rate_pen_up=motion.feed_rate_pen_up,
        feed_rate_pen_down=motion.feed_rate_pen_down,
        pen_up_position=motion.pen_up_position,
        pen_down_position=motion.pen_down_position,
        line_width_calibration=(
            line_width_calibration if line_width_calibration is not None else motion.line_width_calibration
        ),
        blot_delay_calibration=(
            blot_delay_calibration if blot_delay_calibration is not None else motion.blot_delay_calibration
        ),
    )


def _resolve_line_width_range(args: argparse.Namespace, motion: MotionConfig) -> tuple[float, float]:
    min_feed_rate = (
        float(args.min_feed_rate)
        if args.min_feed_rate is not None
        else _prompt_float_with_default("Minimum XY feed rate for calibration", default=25.0, minimum=1.0)
    )
    max_feed_rate_default = max(float(motion.feed_rate_xy), min_feed_rate + 1.0)
    max_feed_rate = (
        float(args.max_feed_rate)
        if args.max_feed_rate is not None
        else _prompt_float_with_default(
            "Maximum XY feed rate for calibration",
            default=max_feed_rate_default,
            minimum=min_feed_rate + 1.0,
        )
    )
    return min_feed_rate, max_feed_rate


def _resolve_blot_delay_range(args: argparse.Namespace) -> tuple[float, float]:
    min_dwell_ms = (
        float(args.min_dwell_ms)
        if args.min_dwell_ms is not None
        else _prompt_float_with_default("Minimum pen-down dwell in milliseconds", default=100.0, minimum=1.0)
    )
    max_dwell_ms = (
        float(args.max_dwell_ms)
        if args.max_dwell_ms is not None
        else _prompt_float_with_default(
            "Maximum pen-down dwell in milliseconds",
            default=30000.0,
            minimum=min_dwell_ms + 1.0,
        )
    )
    return min_dwell_ms, max_dwell_ms


def _build_line_width_calibration(args: argparse.Namespace, motion: MotionConfig) -> CalibrationModel:
    min_feed_rate, max_feed_rate = _resolve_line_width_range(args, motion)
    feed_rates = _build_sample_values(min_feed_rate, max_feed_rate, args.samples)
    samples: list[CalibrationSample] = []
    plot_origin_bounds = _require_workspace_profile(args)
    current_x_mm = args.offset_x_mm
    current_y_mm = args.offset_y_mm

    with _controller_from_args(args) as controller:
        controller.home()
        controller.pen_up()
        _move_to_plot_origin(controller, plot_origin_bounds)
        _prompt_ready(
            "Homing complete. Verify the pen is over the saved plotting origin, place clean paper under the pen, then press Enter to start line-width calibration or q to quit: "
        )
        controller.move_relative(x_mm=current_x_mm, y_mm=current_y_mm)
        print(
            "Drawing line-width samples from the current plotting origin offset with logarithmic spacing across the chosen feed-rate range. Measure each line thickness in mm after it is drawn."
        )

        try:
            for index, feed_rate in enumerate(feed_rates, start=1):
                print(f"Sample {index}/{len(feed_rates)}: drawing {args.line_length_mm:.2f} mm at feed rate {feed_rate:.2f}.")
                controller.pen_down()
                controller.move_relative(x_mm=args.line_length_mm, feed_rate=round(feed_rate))
                controller.pen_up()
                measured_value = _prompt_measured_value(
                    f"Enter measured line width for feed rate {feed_rate:.2f} in mm, or q to quit: "
                )
                samples.append(CalibrationSample(parameter_value=feed_rate, measured_value=measured_value))
                if index < len(feed_rates):
                    controller.move_relative(x_mm=-args.line_length_mm, y_mm=args.line_spacing_mm)
                    current_y_mm += args.line_spacing_mm
        finally:
            controller.pen_up()
            controller.move_relative(x_mm=-current_x_mm, y_mm=-current_y_mm)

    return CalibrationModel.fit(samples)


def _build_blot_delay_calibration(args: argparse.Namespace) -> CalibrationModel:
    min_dwell_ms, max_dwell_ms = _resolve_blot_delay_range(args)
    dwell_values_ms = _build_sample_values(min_dwell_ms, max_dwell_ms, args.samples)
    samples: list[CalibrationSample] = []
    plot_origin_bounds = _require_workspace_profile(args)
    current_x_mm = args.offset_x_mm
    current_y_mm = args.offset_y_mm

    with _controller_from_args(args) as controller:
        controller.home()
        controller.pen_up()
        _move_to_plot_origin(controller, plot_origin_bounds)
        _prompt_ready(
            "Homing complete. Verify the pen is over the saved plotting origin, place clean paper under the pen, then press Enter to start blot-size calibration or q to quit: "
        )
        controller.move_relative(x_mm=current_x_mm, y_mm=current_y_mm)
        print(
            "Creating blot samples from the current plotting origin offset with logarithmic spacing across the chosen dwell range. Measure each blot diameter in mm after it is made."
        )

        try:
            for index, dwell_ms in enumerate(dwell_values_ms, start=1):
                print(f"Sample {index}/{len(dwell_values_ms)}: dwelling for {dwell_ms:.0f} ms.")
                controller.pen_down()
                time.sleep(dwell_ms / 1000.0)
                controller.pen_up()
                measured_value = _prompt_measured_value(
                    f"Enter measured blot diameter for dwell {dwell_ms:.0f} ms in mm, or q to quit: "
                )
                samples.append(CalibrationSample(parameter_value=dwell_ms, measured_value=measured_value))
                if index < len(dwell_values_ms):
                    controller.move_relative(y_mm=args.spot_spacing_mm)
                    current_y_mm += args.spot_spacing_mm
        finally:
            controller.pen_up()
            controller.move_relative(x_mm=-current_x_mm, y_mm=-current_y_mm)

    return CalibrationModel.fit(samples)


def _probe_pen_down(
    controller: DrawCoreController,
    *,
    midpoint: float,
    step: float,
) -> float:
    position = midpoint
    print(
        "Pen-down calibration: each Enter tests a deeper touch by moving to the candidate Z, "
        "then back to the midpoint. Type y when the dot is clear enough, or q to quit."
    )

    while True:
        controller.move_pen(position)
        controller.raw_command("G4 P0.15")
        controller.move_pen(midpoint)

        response = input(f"Dot visible at Z={position}? [y/Enter/q] ").strip().lower()
        if response == "y":
            return position
        if response == "q":
            raise KeyboardInterrupt("Calibration cancelled by user.")

        next_position = clamp_pen_position(position + step)
        if next_position == position:
            print(f"Reached the safe lower limit at Z={PEN_POSITION_MAX}; using that as pen-down.")
            return position
        position = next_position


def _probe_pen_up(
    controller: DrawCoreController,
    *,
    midpoint: float,
    pen_down_position: float,
    step: float,
) -> float:
    position = midpoint
    controller.move_pen(position)
    print(
        "Pen-up calibration: each Enter raises farther from the midpoint. Type y when clearance is good, or q to quit."
    )

    while True:
        response = input(f"Accept pen-up Z={position}? [y/Enter/q] ").strip().lower()
        if response == "y":
            return position
        if response == "q":
            raise KeyboardInterrupt("Calibration cancelled by user.")

        next_position = clamp_pen_position(position - step)
        if next_position == position:
            print(f"Reached the safe upper limit at Z={PEN_POSITION_MIN}; using that as pen-up.")
            return position
        position = next_position
        controller.move_pen(position)

    return pen_down_position


def _prompt_xy_offset(message: str, *, default_x: float = 0.0, default_y: float = 0.0) -> tuple[float, float]:
    x_mm = _prompt_float_with_default(f"{message} X offset in mm", default=default_x)
    y_mm = _prompt_float_with_default(f"{message} Y offset in mm", default=default_y)
    return x_mm, y_mm


def _calibrate_plot_origin_offset(
    controller: DrawCoreController,
    *,
    initial_x_mm: float,
    initial_y_mm: float,
) -> tuple[float, float]:
    candidate_x_mm = initial_x_mm
    candidate_y_mm = initial_y_mm

    print(
        "Plot-origin calibration: enter the distance from machine home to the desired plotting origin."
        " The machine will move there so you can verify the position."
    )

    while True:
        controller.home()
        controller.pen_up()
        candidate_x_mm, candidate_y_mm = _prompt_xy_offset(
            "Distance from machine home to the plotting origin",
            default_x=candidate_x_mm,
            default_y=candidate_y_mm,
        )
        controller.move_relative(x_mm=candidate_x_mm, y_mm=candidate_y_mm)
        response = input(
            f"Accept plotting-origin offset X={candidate_x_mm:g} mm, Y={candidate_y_mm:g} mm? [y/r/q] "
        ).strip().lower()
        if response == "y":
            return candidate_x_mm, candidate_y_mm
        if response == "q":
            raise KeyboardInterrupt("Calibration cancelled by user.")
        controller.move_relative(x_mm=-candidate_x_mm, y_mm=-candidate_y_mm)


def _build_calibrated_motion_config(
    args: argparse.Namespace,
    motion: MotionConfig,
) -> tuple[MotionConfig, WorkspaceBounds]:
    with _controller_from_args(args) as controller:
        seeded_bounds = _seed_workspace_bounds_for_controller(args, controller)
        midpoint = clamp_pen_position(args.midpoint)
        step = max(args.step, 0.05)

        # Steps 1-2: Move XY to the centre of the safe workspace and Z to 0.5 mm.
        center_x_mm = seeded_bounds.width_mm / 2.0
        center_y_mm = seeded_bounds.height_mm / 2.0
        print(
            f"Moving XY to the centre of the safe workspace ({center_x_mm:g} mm, {center_y_mm:g} mm)"
            f" and Z to 5 mm."
        )
        controller.move_relative(x_mm=center_x_mm, y_mm=center_y_mm)
        controller.move_pen(5.0)

        # Step 3: User mounts the pen at 2-4 mm from the bottom (no head movement required).
        _prompt_ready(
            "Mount the pen so the tip is at 2-4 mm from the bottom of the carriage,"
            " then press Enter to home or q to quit: "
        )

        # Step 4: Determine the plot origin programmatically.
        origin_offset_x_mm, origin_offset_y_mm = _calibrate_plot_origin_offset(
            controller,
            initial_x_mm=seeded_bounds.origin_offset_x_mm,
            initial_y_mm=seeded_bounds.origin_offset_y_mm,
        )

        # Step 5: Pen-down / pen-up calibration.
        pen_down_position = _probe_pen_down(controller, midpoint=midpoint, step=step)
        pen_up_position = _probe_pen_up(
            controller,
            midpoint=midpoint,
            pen_down_position=pen_down_position,
            step=step,
        )

    return (
        MotionConfig(
            feed_rate_xy=motion.feed_rate_xy,
            feed_rate_pen_up=motion.feed_rate_pen_up,
            feed_rate_pen_down=motion.feed_rate_pen_down,
            pen_up_position=pen_up_position,
            pen_down_position=pen_down_position,
        ),
        WorkspaceBounds(
            model=seeded_bounds.model,
            width_mm=seeded_bounds.width_mm,
            height_mm=seeded_bounds.height_mm,
            origin_offset_x_mm=origin_offset_x_mm,
            origin_offset_y_mm=origin_offset_y_mm,
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pydrawcore")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="List connected DrawCore devices")
    discover.set_defaults(handler=_cmd_discover)

    info = subparsers.add_parser("info", help="Read firmware, nickname, and status")
    _add_port_argument(info)
    _add_config_dir_argument(info)
    info.set_defaults(handler=_cmd_info)

    remember_model = subparsers.add_parser(
        "remember-model",
        help="Persist a model preset for the currently connected DrawCore device",
    )
    _add_port_argument(remember_model)
    _add_config_dir_argument(remember_model)
    remember_model.add_argument(
        "--model",
        choices=sorted(DRAWCORE_WORKSPACE_PRESETS.keys()),
        required=True,
        help="Model preset to associate with this device's hardware ID",
    )
    remember_model.set_defaults(handler=_cmd_remember_model)

    pen_up = subparsers.add_parser("pen-up", help="Raise the pen")
    _add_port_argument(pen_up)
    _add_motion_config_argument(pen_up)
    _add_config_dir_argument(pen_up)
    pen_up.set_defaults(handler=_cmd_pen_up)

    pen_down = subparsers.add_parser("pen-down", help="Lower the pen")
    _add_port_argument(pen_down)
    _add_motion_config_argument(pen_down)
    _add_config_dir_argument(pen_down)
    pen_down.set_defaults(handler=_cmd_pen_down)

    move = subparsers.add_parser("move-relative", help="Move relative in physical units")
    _add_port_argument(move)
    _add_motion_config_argument(move)
    _add_config_dir_argument(move)
    move.add_argument("--x-mm", type=float, default=0.0)
    move.add_argument("--y-mm", type=float, default=0.0)
    move.add_argument("--feed-rate", type=int, default=1200, help="Native DrawCore feed rate")
    move.set_defaults(handler=_cmd_move)

    mark_bounds = subparsers.add_parser(
        "mark-bounds",
        help="Draw a rectangular XY workspace boundary using the selected DrawCore model bounds",
    )
    _add_port_argument(mark_bounds)
    _add_motion_config_argument(mark_bounds)
    _add_workspace_config_argument(mark_bounds)
    _add_config_dir_argument(mark_bounds)
    mark_bounds.add_argument(
        "--model",
        choices=sorted(DRAWCORE_WORKSPACE_PRESETS.keys()),
        default=None,
        help="DrawCore model preset used for workspace bounds; when provided, this overrides any saved workspace profile",
    )
    mark_bounds.add_argument("--width-mm", type=float, help="Override workspace width in millimeters")
    mark_bounds.add_argument("--height-mm", type=float, help="Override workspace height in millimeters")
    mark_bounds.add_argument(
        "--inset-mm",
        type=float,
        default=5.0,
        help="Inset the rectangle from the machine limits by this many millimeters",
    )
    mark_bounds.add_argument(
        "--skip-home",
        action="store_true",
        help="Use the current XY origin instead of homing first",
    )
    mark_bounds.add_argument(
        "--use-model-preset",
        action="store_true",
        help="Ignore any saved workspace profile and use the selected or inferred rig model preset instead",
    )
    mark_bounds.set_defaults(handler=_cmd_mark_bounds)

    calibrate_xy = subparsers.add_parser(
        "calibrate-xy",
        help="Measure machine-specific X and Y workspace extents from a known plotting origin",
    )
    _add_port_argument(calibrate_xy)
    _add_motion_config_argument(calibrate_xy)
    _add_workspace_config_argument(calibrate_xy)
    _add_config_dir_argument(calibrate_xy)
    calibrate_xy.add_argument(
        "--model",
        choices=sorted(DRAWCORE_WORKSPACE_PRESETS.keys()),
        default="default",
        help="DrawCore model preset used as the safe maximum workspace envelope",
    )
    calibrate_xy.add_argument("--max-x-mm", type=float, help="Safe maximum X travel to allow during calibration")
    calibrate_xy.add_argument("--max-y-mm", type=float, help="Safe maximum Y travel to allow during calibration")
    calibrate_xy.add_argument(
        "--step-mm",
        type=float,
        default=10.0,
        help="Base increment for XY calibration; Enter moves +step, h moves +step/2, b moves -step, bh moves -step/2, and typed signed deltas are clamped to the safe envelope",
    )
    calibrate_xy.add_argument(
        "--output",
        help="Write the calibrated workspace profile to this JSON file",
    )
    calibrate_xy.set_defaults(handler=_cmd_calibrate_xy)

    home = subparsers.add_parser("home", help="Run the native DrawCore homing command")
    _add_port_argument(home)
    home.set_defaults(handler=_cmd_home)

    raw_query = subparsers.add_parser("raw-query", help="Send a raw DrawCore query")
    _add_port_argument(raw_query)
    raw_query.add_argument("query")
    raw_query.set_defaults(handler=_cmd_raw_query)

    raw_command = subparsers.add_parser("raw-command", help="Send a raw DrawCore command")
    _add_port_argument(raw_command)
    raw_command.add_argument("command_text")
    raw_command.set_defaults(handler=_cmd_raw_command)

    calibrate_pen = subparsers.add_parser(
        "calibrate-pen",
        help="Interactively find pen-up clearance and pen-down contact positions",
    )
    _add_port_argument(calibrate_pen)
    _add_motion_config_argument(calibrate_pen)
    _add_workspace_config_argument(calibrate_pen)
    _add_config_dir_argument(calibrate_pen)
    calibrate_pen.add_argument(
        "--model",
        choices=sorted(DRAWCORE_WORKSPACE_PRESETS.keys()),
        default=None,
        help="Model preset used when seeding a new workspace profile for plotting-origin calibration",
    )
    calibrate_pen.add_argument(
        "--midpoint",
        type=float,
        default=(PEN_POSITION_MIN + PEN_POSITION_MAX) / 2,
        help="Safe staging Z used during calibration",
    )
    calibrate_pen.add_argument(
        "--step",
        type=float,
        default=0.5,
        help="Z increment used while probing pen-down and pen-up positions",
    )
    calibrate_pen.add_argument(
        "--output",
        help="Write the calibrated motion profile to this JSON file",
    )
    calibrate_pen.set_defaults(handler=_cmd_calibrate_pen)

    calibrate_line_width = subparsers.add_parser(
        "calibrate-line-width",
        help="Draw line samples at different feed rates and fit a line-width calibration model",
    )
    _add_port_argument(calibrate_line_width)
    _add_motion_config_argument(calibrate_line_width)
    _add_workspace_config_argument(calibrate_line_width)
    _add_config_dir_argument(calibrate_line_width)
    calibrate_line_width.add_argument("--samples", type=int, default=5, help="Number of feed-rate samples to draw")
    calibrate_line_width.add_argument(
        "--min-feed-rate",
        type=float,
        default=None,
        help="Lowest XY feed rate to sample; if omitted, the command prompts and defaults to 25",
    )
    calibrate_line_width.add_argument(
        "--max-feed-rate",
        type=float,
        default=None,
        help="Highest XY feed rate to sample; if omitted, the command prompts and defaults to the motion profile XY feed rate",
    )
    calibrate_line_width.add_argument(
        "--line-length-mm",
        type=float,
        default=20.0,
        help="Physical length of each calibration line",
    )
    calibrate_line_width.add_argument(
        "--line-spacing-mm",
        type=float,
        default=8.0,
        help="Vertical spacing between calibration lines",
    )
    calibrate_line_width.add_argument(
        "--offset-x-mm",
        type=float,
        default=20.0,
        help="Initial X offset from the current plotting origin",
    )
    calibrate_line_width.add_argument(
        "--offset-y-mm",
        type=float,
        default=20.0,
        help="Initial Y offset from the current plotting origin",
    )
    calibrate_line_width.add_argument(
        "--output",
        help="Write the calibrated motion profile to this JSON file",
    )
    calibrate_line_width.set_defaults(handler=_cmd_calibrate_line_width)

    calibrate_blot_size = subparsers.add_parser(
        "calibrate-blot-size",
        help="Create dwell-based blot samples and fit a blot-size calibration model",
    )
    _add_port_argument(calibrate_blot_size)
    _add_motion_config_argument(calibrate_blot_size)
    _add_workspace_config_argument(calibrate_blot_size)
    _add_config_dir_argument(calibrate_blot_size)
    calibrate_blot_size.add_argument("--samples", type=int, default=5, help="Number of dwell samples to create")
    calibrate_blot_size.add_argument(
        "--min-dwell-ms",
        type=float,
        default=None,
        help="Shortest pen-down dwell to sample, in milliseconds; if omitted, the command prompts and defaults to 100",
    )
    calibrate_blot_size.add_argument(
        "--max-dwell-ms",
        type=float,
        default=None,
        help="Longest pen-down dwell to sample, in milliseconds; if omitted, the command prompts and defaults to 30000",
    )
    calibrate_blot_size.add_argument(
        "--spot-spacing-mm",
        type=float,
        default=8.0,
        help="Vertical spacing between blot samples",
    )
    calibrate_blot_size.add_argument(
        "--offset-x-mm",
        type=float,
        default=20.0,
        help="Initial X offset from the current plotting origin",
    )
    calibrate_blot_size.add_argument(
        "--offset-y-mm",
        type=float,
        default=20.0,
        help="Initial Y offset from the current plotting origin",
    )
    calibrate_blot_size.add_argument(
        "--output",
        help="Write the calibrated motion profile to this JSON file",
    )
    calibrate_blot_size.set_defaults(handler=_cmd_calibrate_blot_size)

    run_program_parser = subparsers.add_parser(
        "run-program",
        help="Parse and execute a turtle-style drawing program",
    )
    _add_port_argument(run_program_parser)
    _add_motion_config_argument(run_program_parser)
    _add_workspace_config_argument(run_program_parser)
    _add_config_dir_argument(run_program_parser)
    run_program_parser.add_argument("program", help="Path to the program text file")
    run_program_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse the program and print the normalized command structure without moving hardware",
    )
    run_program_parser.add_argument(
        "--preview",
        action="store_true",
        help="Compile the program to motion operations JSON without moving hardware",
    )
    run_program_parser.add_argument(
        "--export-svg",
        help="Write an SVG preview of the compiled path instead of moving hardware",
    )
    run_program_parser.add_argument(
        "--start-heading",
        type=float,
        default=0.0,
        help="Initial turtle heading in degrees; zero points along positive X",
    )
    run_program_parser.add_argument(
        "--circle-segment-length-mm",
        type=float,
        default=1.0,
        help="Approximate stroked circles with segments of roughly this length in millimeters",
    )
    run_program_parser.set_defaults(handler=_cmd_run_program)

    return parser


def _cmd_discover(_args: argparse.Namespace) -> int:
    print(json.dumps([asdict(device) for device in discover_devices()], indent=2))
    return 0


def _cmd_info(args: argparse.Namespace) -> int:
    with _controller_from_args(args) as controller:
        info = asdict(controller.get_device_info())
        device = _find_connected_device(controller.port_name)
        if device is not None:
            info["description"] = device.description
            info["hwid"] = device.hwid
            info["remembered_model"] = _remembered_model_for_device(args, device)
            info["resolved_model"] = info["remembered_model"] or info.get("inferred_model")
        print(json.dumps(info, indent=2))
    return 0


def _cmd_remember_model(args: argparse.Namespace) -> int:
    with _controller_from_args(args) as controller:
        device = _find_connected_device(controller.port_name)
        if device is None:
            raise ValueError(
                "Unable to determine the connected DrawCore device identity. Pass --port for a single connected rig."
            )

    model_map = _load_device_model_map(args)
    model_map[device.hwid] = args.model
    output_path = _save_device_model_map(args, model_map)
    print(
        json.dumps(
            {
                "port": device.port,
                "hwid": device.hwid,
                "model": args.model,
                "saved_to": str(output_path),
            },
            indent=2,
        )
    )
    return 0


def _cmd_pen_up(args: argparse.Namespace) -> int:
    with _controller_from_args(args) as controller:
        controller.pen_up()
    return 0


def _cmd_pen_down(args: argparse.Namespace) -> int:
    with _controller_from_args(args) as controller:
        controller.pen_down()
    return 0


def _cmd_move(args: argparse.Namespace) -> int:
    with _controller_from_args(args) as controller:
        controller.move_relative(x_mm=args.x_mm, y_mm=args.y_mm, feed_rate=args.feed_rate)
    return 0


def _cmd_mark_bounds(args: argparse.Namespace) -> int:
    bounds = _resolve_workspace_bounds(args)
    _mark_workspace_bounds(args, bounds)
    print(
        json.dumps(
            {
                "model": bounds.model,
                "width_mm": bounds.width_mm,
                "height_mm": bounds.height_mm,
                "origin_offset_x_mm": bounds.origin_offset_x_mm,
                "origin_offset_y_mm": bounds.origin_offset_y_mm,
                "inset_mm": max(args.inset_mm, 0.0),
                "home_first": not args.skip_home,
            },
            indent=2,
        )
    )
    return 0


def _cmd_home(args: argparse.Namespace) -> int:
    with _controller_from_args(args) as controller:
        controller.home()
    return 0


def _cmd_raw_query(args: argparse.Namespace) -> int:
    with _controller_from_args(args) as controller:
        print(controller.raw_query(args.query).strip())
    return 0


def _cmd_raw_command(args: argparse.Namespace) -> int:
    with _controller_from_args(args) as controller:
        controller.raw_command(args.command_text)
    return 0


def _cmd_calibrate_pen(args: argparse.Namespace) -> int:
    motion = _motion_from_args(args) or MotionConfig()
    calibrated_motion, calibrated_workspace = _build_calibrated_motion_config(args, motion)
    print(json.dumps(asdict(calibrated_motion), indent=2))
    output_path = _save_motion_profile(args, calibrated_motion)
    workspace_path = _save_workspace_profile(args, calibrated_workspace, use_output_path=False)
    print(f"Saved motion profile to {output_path}")
    print(f"Saved workspace profile to {workspace_path}")
    return 0


def _cmd_calibrate_xy(args: argparse.Namespace) -> int:
    calibrated_bounds = _build_calibrated_workspace_bounds(args)
    print(json.dumps(asdict(calibrated_bounds), indent=2))
    output_path = _save_workspace_profile(args, calibrated_bounds)
    print(f"Saved workspace profile to {output_path}")
    return 0


def _cmd_calibrate_line_width(args: argparse.Namespace) -> int:
    motion = _motion_from_args(args) or MotionConfig()
    calibrated_line_width = _build_line_width_calibration(args, motion)
    calibrated_motion = _motion_with_calibration(motion, line_width_calibration=calibrated_line_width)
    print(json.dumps(asdict(calibrated_motion), indent=2))
    output_path = _save_motion_profile(args, calibrated_motion)
    print(f"Saved motion profile to {output_path}")
    return 0


def _cmd_calibrate_blot_size(args: argparse.Namespace) -> int:
    motion = _motion_from_args(args) or MotionConfig()
    calibrated_blot_size = _build_blot_delay_calibration(args)
    calibrated_motion = _motion_with_calibration(motion, blot_delay_calibration=calibrated_blot_size)
    print(json.dumps(asdict(calibrated_motion), indent=2))
    output_path = _save_motion_profile(args, calibrated_motion)
    print(f"Saved motion profile to {output_path}")
    return 0


def _cmd_run_program(args: argparse.Namespace) -> int:
    program_path = Path(args.program).expanduser().resolve()
    program_text = program_path.read_text(encoding="utf-8")
    program = parse_program(program_text)
    motion = _motion_from_args(args) or MotionConfig()
    if args.dry_run:
        print(json.dumps(program.to_dict(), indent=2))
        return 0

    if args.preview or args.export_svg:
        preview = preview_program(
            motion,
            program_text,
            start_heading_deg=args.start_heading,
            circle_segment_length_mm=args.circle_segment_length_mm,
            return_to_origin=True,
        )
        result: dict[str, object] = {
            "program": str(program_path),
            "commands": len(program.commands),
            "preview": preview.to_dict(),
        }
        if args.export_svg:
            workspace_bounds = _workspace_from_args(args)
            svg_path = export_preview_svg(preview, args.export_svg, workspace_bounds=workspace_bounds)
            result["svg_path"] = str(svg_path)
        print(json.dumps(result, indent=2))
        return 0

    with _controller_from_args(args) as controller:
        workspace_bounds = _workspace_from_args(args)
        if workspace_bounds is not None:
            check_program_fits_workspace(
                motion,
                program_text,
                workspace_bounds,
                start_heading_deg=args.start_heading,
                circle_segment_length_mm=args.circle_segment_length_mm,
            )
        runner = ProgramRunner(
            controller=controller,
            motion=motion,
            circle_segment_length_mm=args.circle_segment_length_mm,
            state=TurtleState(heading_deg=args.start_heading % 360.0),
        )
        controller.pen_up()
        try:
            runner.run(program)
        finally:
            controller.pen_up()
            runner.return_to_origin()
    print(json.dumps({"program": str(program_path), "commands": len(program.commands)}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Callable[[argparse.Namespace], int] = args.handler
    try:
        return handler(args)
    except ProgramError as exc:
        parser.exit(status=2, message=f"{exc}\n")
