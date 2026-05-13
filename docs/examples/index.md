# Examples

The repository already ships with three sample turtle programs under `examples/turtle/`. They are intended to cover the current DSL surface without requiring custom authoring before your first run.

## What each example covers

| File | Focus |
| --- | --- |
| `feature_smoke.draw` | Every currently supported command at least once |
| `calibrated_marks.draw` | Width-controlled lines and dwell-based blots |
| `repeat_rosette.draw` | Heading control, repeat blocks, and circles |

## Suggested commands

```powershell
python -m pydrawcore run-program examples/turtle/feature_smoke.draw --dry-run
python -m pydrawcore run-program examples/turtle/feature_smoke.draw
python -m pydrawcore run-program examples/turtle/calibrated_marks.draw
python -m pydrawcore run-program examples/turtle/repeat_rosette.draw
```

If any width or blot size is outside your measured calibration range, edit the numeric values in the program file or update the saved motion profile.
