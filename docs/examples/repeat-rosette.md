# Repeat Rosette

This example focuses on repeated strokes, heading changes, and circular geometry.

## Program

```text
# Demonstrates heading control, circles, direct XY moves, and nested repeated strokes.

HOME
MOVE 80 80
SETHEADING 0

REPEAT 6
FORWARD 20 WIDTH 0.7
BACK 20 WIDTH 0.7
RIGHT 60
END

MOVE 120 80
CIRCLE 22 WIDTH 0.7

MOVE 160 80
REPEAT 8
FORWARD 14 WIDTH 0.7
RIGHT 45
END
```

## Why run it

Use this to validate repeat-block execution and heading arithmetic, especially after changes to the program runner or motion conversion logic.
