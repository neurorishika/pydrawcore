# PyDrawCore

`pydrawcore` is a standalone, pip-ready Python package for controlling DrawCore-based writing robots without Inkscape.

It provides:

- a typed Python API for discovery, connection, pen control, homing, motion, and board queries
- an interactive pen calibration workflow that produces reusable motion profiles
- interactive ink calibration workflows for line width versus speed and blot size versus dwell
- a small CLI for production and ops workflows
- a raw command escape hatch for unsupported DrawCore commands
- unit tests that validate command formatting and controller behavior without hardware

## Why this package exists

The bundled Inkscape extension in `extensions/` is coupled to `inkex` and vendored XML dependencies. This package bypasses that stack and talks to DrawCore controllers directly over serial.

## Installation

Editable install for development:

```bash
pip install -e .[dev]
```

Regular install:

```bash
pip install .
```

## Documentation

The repository now includes a Material for MkDocs documentation site with getting-started guides, CLI workflows, turtle DSL coverage, examples, and generated API reference.

Build it locally with:

```bash
pip install -e .[docs]
mkdocs serve
```

Create a static site with:

```bash
mkdocs build
```

## CLI usage

List compatible devices:

```bash
pydrawcore discover
```

Read board information:

```bash
pydrawcore info
pydrawcore info --port COM4
```

Persist a model preset for a specific rig when the controller does not expose a nickname-derived model:

```bash
pydrawcore remember-model --port COM4 --model v3a3
pydrawcore info --port COM4
```

Enable motors and move 10 mm in X:

```bash
pydrawcore move-relative --x-mm 10 --speed 1200
```

Mark the XY workspace bounds using the same model-based travel limits that the Inkscape extension uses:

```bash
pydrawcore mark-bounds --port COM4 --model default
pydrawcore mark-bounds --port COM4 --model v3a3 --inset-mm 5
```

Measure the machine-specific X and Y workspace from a known plotting origin and save it for later safe bound marking:

```bash
pydrawcore calibrate-xy --port COM4 --step-mm 10
```

Pen control:

```bash
pydrawcore pen-up
pydrawcore pen-down
pydrawcore calibrate-pen --port COM4 --midpoint 5.0 --step 0.5
pydrawcore calibrate-line-width --port COM4 --samples 5 --min-feed-rate 25 --max-feed-rate 1200
pydrawcore calibrate-blot-size --port COM4 --samples 5 --min-dwell-ms 100 --max-dwell-ms 30000
```

Pen Z values are clamped to the same safe `0.0..10.0` range used by the Inkscape extension.
`calibrate-pen` now does two things in one pass: it captures the plotting-origin offset from raw machine home, and then it stages at a safe midpoint, probes pen-down by touching and returning to midpoint until a dot is visible, then raises progressively until pen-up clearance is acceptable.
The plotting-origin offset is saved in `~/.drawcore/workspace.json` and defines the writable origin as `home + offset`. `mark-bounds`, `calibrate-xy`, `calibrate-line-width`, and `calibrate-blot-size` all home the machine and then move to that saved plotting origin before drawing. Use `--skip-home` on `mark-bounds` only when the machine is already positioned at the plotting origin.
If you omit the min and max flags, the line-width and blot-size commands prompt for them at runtime so you can choose the practical range for the current pen and paper. Sample points are distributed logarithmically across the chosen range, and saved calibration uses piecewise linear interpolation over the recorded samples.
By default, motion profiles are saved to and loaded from `~/.drawcore/motion.json`. Use `--config-dir` to change that machine-local directory or `--motion-config` to point at a specific JSON file.
Measured workspace profiles and plotting-origin offsets are saved to and loaded from `~/.drawcore/workspace.json` by default. Run `calibrate-pen` before other plot-space calibration commands so the saved plotting origin is available.
If the rig does not report a nickname, you can persist a model per device in `~/.drawcore/devices.json` with `remember-model`.
Workspace bounds in `pydrawcore` are plot-space bounds, matching the extension-facing plotting frame rather than raw DrawCore machine-axis coordinates.

Use a saved motion profile for later runs:

```bash
pydrawcore pen-up --port COM4
pydrawcore pen-down --port COM4
pydrawcore pen-up --port COM4 --config-dir D:/robot/profiles
pydrawcore pen-down --port COM4 --motion-config motion.json
```

Low-level access:

```bash
pydrawcore raw-query V
pydrawcore raw-command "$H"
```

## Python usage

```python
from pydrawcore import DrawCoreController, workspace_bounds_for_model

with DrawCoreController.auto_connect() as robot:
    print(robot.get_device_info())
    print(workspace_bounds_for_model("default"))
    robot.pen_up()
    robot.move_relative(x_mm=20, y_mm=0, feed_rate=1200)
    robot.pen_down()
    robot.move_relative(x_mm=0, y_mm=10, feed_rate=600)
    robot.pen_up()
    robot.home()
```

## API surface

The package exposes:

- serial discovery
- firmware and status queries
- workspace-bound dataclasses and model preset helpers
- pen up and pen down
- interactive pen-up and pen-down calibration with JSON profile output
- line-width versus feed-rate calibration with fitted lookup helpers
- blot-size versus dwell calibration with fitted lookup helpers
- model-based XY workspace bounds and a boundary-marking CLI pattern
- native DrawCore homing
- relative XY moves in inches or millimeters
- raw query and raw command methods

## Notes

This package is DrawCore-only. Legacy EBB/AxiDraw compatibility has been removed from the installable package surface.
