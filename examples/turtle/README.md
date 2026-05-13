These sample programs target the current turtle-style DSL in `pydrawcore run-program`.

They assume you already have a calibrated motion profile at the default config path `~/.drawcore/motion.json` or that you will pass `--motion-config` explicitly.

Suggested commands:

```powershell
c:/Rishika/Trailobot/.venv/Scripts/python.exe -m pydrawcore run-program examples/turtle/feature_smoke.draw
c:/Rishika/Trailobot/.venv/Scripts/python.exe -m pydrawcore run-program examples/turtle/calibrated_marks.draw
c:/Rishika/Trailobot/.venv/Scripts/python.exe -m pydrawcore run-program examples/turtle/repeat_rosette.draw
```

Dry-run first when you only want to verify parsing:

```powershell
c:/Rishika/Trailobot/.venv/Scripts/python.exe -m pydrawcore run-program examples/turtle/feature_smoke.draw --dry-run
```

Notes:

- `feature_smoke.draw` touches every command we support right now.
- `calibrated_marks.draw` focuses on width-controlled lines and dwell-based blots.
- `repeat_rosette.draw` focuses on turtle heading, repeat blocks, and circles.
- If any width or blot size is outside your measured calibration range, lower or raise the numeric values in the program file until they fall inside your profile.