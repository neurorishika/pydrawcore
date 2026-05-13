These sample programs target the current turtle-style DSL in `pydrawcore run-program`.

They assume you already have a calibrated motion profile at the default config path `~/.drawcore/motion.json` or that you will pass `--motion-config` explicitly.

The current saved calibration on this workstation covers:

- line widths from `0.3` mm to `2.5` mm
- blot sizes from `0.1` mm to `3.5` mm

Suggested commands:

```powershell
c:/Rishika/Trailobot/.venv/Scripts/python.exe -m pydrawcore run-program examples/turtle/feature_smoke.draw
c:/Rishika/Trailobot/.venv/Scripts/python.exe -m pydrawcore run-program examples/turtle/calibrated_marks.draw
c:/Rishika/Trailobot/.venv/Scripts/python.exe -m pydrawcore run-program examples/turtle/repeat_rosette.draw
c:/Rishika/Trailobot/.venv/Scripts/python.exe -m pydrawcore run-program examples/turtle/petal_flower.draw
c:/Rishika/Trailobot/.venv/Scripts/python.exe -m pydrawcore run-program examples/turtle/material_test_card.draw
```

Dry-run first when you only want to verify parsing:

```powershell
c:/Rishika/Trailobot/.venv/Scripts/python.exe -m pydrawcore run-program examples/turtle/feature_smoke.draw --dry-run
```

Preview the compiled toolpath without touching the rig:

```powershell
c:/Rishika/Trailobot/.venv/Scripts/python.exe -m pydrawcore run-program examples/turtle/material_test_card.draw --preview
c:/Rishika/Trailobot/.venv/Scripts/python.exe -m pydrawcore run-program examples/turtle/material_test_card.draw --export-svg examples/turtle/material_test_card.svg
```

Notes:

- `feature_smoke.draw` touches every command we support right now, including `SETWIDTH` and clearing it with `SETWIDTH NONE`.
- `calibrated_marks.draw` focuses on width-controlled lines and dwell-based blots inside the current saved calibration range.
- `repeat_rosette.draw` focuses on turtle heading, repeat blocks, circles, and changing default width mid-pattern.
- `petal_flower.draw` is a more artistic repeat-based composition with width changes and orbit circles.
- `material_test_card.draw` is tailored to the current saved calibration range and includes the exact measured width and blot endpoints.
- `--dry-run` shows parsed commands, `--preview` shows compiled motion operations, and `--export-svg` writes an SVG path preview.