# PyDrawCore

PyDrawCore is a standalone Python package for controlling DrawCore writing robots without the Inkscape extension stack. It is built for direct serial control, machine-local calibration data, and automation-friendly scripting.

## Why this documentation exists

The repository already contains three distinct surfaces:

- a small typed Python API for connection, motion, discovery, and program execution
- a production-oriented CLI for calibration and operational workflows
- a turtle-style drawing DSL with example programs in `examples/turtle/`

This site organizes those surfaces so you can move from installation to a first plot, then into calibration, automation, and the generated API reference.

## Core capabilities

<div class="grid cards" markdown>

- ### Direct machine control

  Connect over serial, query firmware and status, home the rig, and move in plot-space millimeters or inches.

- ### Calibrated pen motion

  Save pen positions, line-width curves, blot dwell curves, and workspace profiles to reusable JSON files.

- ### Automation-friendly CLI

  Run discovery, info, motion, calibration, and program execution commands without pulling in Inkscape.

- ### Turtle-style program runner

  Parse and execute repeatable `.draw` programs for simple geometry, calibration sheets, and plotting experiments.

</div>

## Recommended reading order

1. Start with [Installation](getting-started/installation.md) to install docs and runtime dependencies.
2. Follow [Quickstart](getting-started/quickstart.md) for the shortest path to device discovery and a first drawing motion.
3. Use [CLI Workflows](guides/cli.md) when you need calibration, workspace setup, or repeatable operator commands.
4. Use [Turtle DSL](guides/turtle-dsl.md) and the [Examples](examples/index.md) section when you want programmable drawing patterns.
5. Drop into the [API Reference](api/index.md) when you need signatures, dataclasses, and module-level behavior.

## Architecture at a glance

```text
PyDrawCore
|- discovery       Detect compatible serial devices
|- controller      Send DrawCore motion and query commands
|- models          Persist motion, calibration, and workspace data
|- program         Parse and run turtle-style drawing files
`- cli             Expose automation and operator workflows
```

## Build the docs locally

```bash
pip install -e .[docs]
mkdocs serve
```

Material for MkDocs is configured with generated API pages through `mkdocstrings`, so local builds stay aligned with the package surface in `src/pydrawcore`.
