# Quickstart

## 1. Discover a controller

Start by listing compatible serial devices:

```bash
pydrawcore discover
```

If only one device is connected, most CLI flows can auto-select it. Otherwise pass `--port`, for example `--port COM4`.

## 2. Read board information

Use the info command to confirm communication and inspect inferred model details:

```bash
pydrawcore info
pydrawcore info --port COM4
```

## 3. Calibrate motion once

The controller and several CLI commands can operate with defaults, but production use is better with a saved motion profile:

```bash
pydrawcore calibrate-pen --port COM4 --midpoint 5.0 --step 0.5
```

The default machine-local location is `~/.drawcore/motion.json`.

## 4. Make a first move

Raise the pen, move in plot space, then lower it again:

```bash
pydrawcore pen-up --port COM4
pydrawcore move-relative --port COM4 --x-mm 10 --y-mm 0 --speed 1200
pydrawcore pen-down --port COM4
```

Positive `x_mm` moves right. Positive plot-space `y_mm` moves downward on the page abstraction, while the controller internally converts that to the machine-axis command format expected by DrawCore firmware.

## 5. Run a sample program

Dry-run a turtle program first to verify parsing and command expansion:

```bash
python -m pydrawcore run-program examples/turtle/feature_smoke.draw --dry-run
```

Then execute it against hardware once your motion profile is ready:

```bash
python -m pydrawcore run-program examples/turtle/feature_smoke.draw
```

## Equivalent Python API

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

## Next steps

- Use [CLI Workflows](../guides/cli.md) for calibration and workspace setup.
- Use [Turtle DSL](../guides/turtle-dsl.md) to understand `.draw` programs.
- Use [API Reference](../api/index.md) for module-level details.
