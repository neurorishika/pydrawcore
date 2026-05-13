# Turtle DSL

PyDrawCore includes a small turtle-style language for repeatable drawings and calibration sheets. Programs are plain text files, usually with the `.draw` extension.

## Supported commands

| Command | Purpose |
| --- | --- |
| `HOME` | Home the machine and reset the runner position to `(0, 0)` |
| `PENUP` | Raise the pen using the active motion profile |
| `PENDOWN` | Lower the pen using the active motion profile |
| `SETHEADING angle` | Set the turtle heading in degrees |
| `LEFT angle` | Rotate heading counterclockwise |
| `RIGHT angle` | Rotate heading clockwise |
| `MOVE x y` | Travel to an absolute plot-space coordinate with pen up |
| `LINE x y WIDTH w` | Draw to an absolute coordinate with optional calibrated width |
| `FORWARD d WIDTH w` | Draw forward along the current heading |
| `BACK d WIDTH w` | Draw backward along the current heading |
| `BLOT size` | Draw a blot using calibrated dwell time |
| `CIRCLE diameter WIDTH w` | Approximate a circle from the current center point |
| `REPEAT n ... END` | Repeat a block of child commands |

## Example

```text
HOME
MOVE 20 20
SETHEADING 0

REPEAT 4
FORWARD 12 WIDTH 0.7
RIGHT 90
END
```

## Execution model

- Comments begin with `#` and are ignored.
- Parsing is line-based and preserves line numbers for errors.
- `REPEAT` creates nested child commands and requires a matching `END`.
- Heading-based motion is resolved in millimeters before the controller receives relative XY commands.
- `WIDTH` and blot size values are validated against the current `MotionConfig` calibration models.

## Dry-run vs hardware execution

Use `--dry-run` from the CLI to validate syntax and command expansion without sending movement commands to a device.

## Error behavior

Parser and execution failures raise `ProgramError`, which includes the originating line number when available. This is especially useful when a width or blot request falls outside your measured calibration range.

## Related examples

- [Feature Smoke](../examples/feature-smoke.md)
- [Calibrated Marks](../examples/calibrated-marks.md)
- [Repeat Rosette](../examples/repeat-rosette.md)
