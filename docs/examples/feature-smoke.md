# Feature Smoke

This example touches every command supported by the current turtle DSL.

## Program

```text
# Exercises every currently supported command at least once.

HOME
MOVE 20 20
PENDOWN
PENUP

SETHEADING 0
FORWARD 24 WIDTH 0.7
LEFT 90
FORWARD 18 WIDTH 0.7
RIGHT 135
BACK 12 WIDTH 0.7

MOVE 65 28
LINE 95 28 WIDTH 0.7
BLOT 0.8

MOVE 125 28
CIRCLE 16 WIDTH 0.7

MOVE 165 20
SETHEADING 0
REPEAT 4
FORWARD 12 WIDTH 0.7
RIGHT 90
END
```

## Why run it

Use this file as a parser smoke test, a machine-validation sheet, or a post-calibration sanity check after changing motion profiles.
