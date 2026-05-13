# CLI Workflows

The CLI is designed for operator-grade workflows: discovery, inspection, machine calibration, workspace setup, and repeatable execution.

## Discovery and inspection

```bash
pydrawcore discover
pydrawcore info --port COM4
```

Use `remember-model` when a rig does not expose a nickname-derived model:

```bash
pydrawcore remember-model --port COM4 --model v3a3
```

## Pen motion and direct movement

```bash
pydrawcore pen-up --port COM4
pydrawcore pen-down --port COM4
pydrawcore move-relative --port COM4 --x-mm 10 --y-mm 5 --speed 1200
```

Pen Z positions are clamped to the same safe `0.0..10.0` range used by the extension ecosystem.

## Calibration workflows

### Pen position calibration

```bash
pydrawcore calibrate-pen --port COM4 --midpoint 5.0 --step 0.5
```

This workflow captures the plotting-origin offset from raw machine home and saves the resulting workspace origin for later commands.

### Line width calibration

```bash
pydrawcore calibrate-line-width --port COM4 --samples 5 --min-feed-rate 25 --max-feed-rate 1200
```

### Blot size calibration

```bash
pydrawcore calibrate-blot-size --port COM4 --samples 5 --min-dwell-ms 100 --max-dwell-ms 30000
```

Both calibration commands build piecewise interpolation models over the measured samples and persist them to the motion profile.

## Workspace workflows

Mark bounds using a saved workspace profile or a model preset:

```bash
pydrawcore mark-bounds --port COM4 --model default
pydrawcore mark-bounds --port COM4 --model v3a3 --inset-mm 5
```

Measure and save a machine-specific plotting area:

```bash
pydrawcore calibrate-xy --port COM4 --step-mm 10
```

These commands operate in plot-space bounds, matching the extension-facing plotting frame rather than raw machine-axis coordinates.

## Motion and workspace config files

By default, machine-local files live under `~/.drawcore/`:

- `motion.json` for pen and calibration data
- `workspace.json` for plotting origin offsets and measured bounds
- `devices.json` for remembered device-to-model mappings

Override that location per command:

```bash
pydrawcore pen-up --port COM4 --config-dir D:/robot/profiles
pydrawcore pen-down --port COM4 --motion-config motion.json
```

## Raw commands

Use raw access when firmware supports a command not yet wrapped by the high-level API:

```bash
pydrawcore raw-query V
pydrawcore raw-command "$H"
```

## Program execution

The CLI exposes the turtle-style DSL through `run-program`.

Dry-run first when you only want parser validation:

```bash
python -m pydrawcore run-program examples/turtle/feature_smoke.draw --dry-run
```

When widths or blot sizes are outside your saved calibration range, program execution fails fast with a line-numbered `ProgramError`.
