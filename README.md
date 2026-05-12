# PyDrawCore

`pydrawcore` is a standalone, pip-ready Python package for controlling DrawCore-based writing robots without Inkscape.

It provides:

- a typed Python API for discovery, connection, pen control, homing, motion, and board queries
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

Enable motors and move 10 mm in X:

```bash
pydrawcore move-relative --x-mm 10 --speed 1200
```

Pen control:

```bash
pydrawcore pen-up
pydrawcore pen-down
```

Low-level access:

```bash
pydrawcore raw-query V
pydrawcore raw-command "$H"
```

## Python usage

```python
from pydrawcore import DrawCoreController

with DrawCoreController.auto_connect() as robot:
    print(robot.get_device_info())
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
- pen up and pen down
- native DrawCore homing
- relative XY moves in inches or millimeters
- raw query and raw command methods

## Notes

This package is DrawCore-only. Legacy EBB/AxiDraw compatibility has been removed from the installable package surface.

