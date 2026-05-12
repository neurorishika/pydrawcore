from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


PEN_POSITION_MIN = 0.0
PEN_POSITION_MAX = 10.0
MM_PER_INCH = 25.4


def clamp_pen_position(position: float) -> float:
    return max(PEN_POSITION_MIN, min(PEN_POSITION_MAX, float(position)))


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _linear_interpolate(x0: float, y0: float, x1: float, y1: float, x_value: float) -> float:
    if x1 == x0:
        return y0
    return y0 + ((x_value - x0) * (y1 - y0) / (x1 - x0))


def _drop_none_values(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _drop_none_values(nested_value)
            for key, nested_value in value.items()
            if nested_value is not None
        }
    if isinstance(value, list):
        return [_drop_none_values(item) for item in value]
    return value


@dataclass(slots=True, frozen=True)
class CalibrationSample:
    parameter_value: float
    measured_value: float

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> "CalibrationSample":
        return cls(
            parameter_value=float(data["parameter_value"]),
            measured_value=float(data["measured_value"]),
        )


@dataclass(slots=True)
class CalibrationModel:
    samples: list[CalibrationSample] = field(default_factory=list)
    fit_kind: str = "piecewise"
    slope: float | None = None
    intercept: float | None = None
    max_abs_error: float | None = None
    rmse: float | None = None
    parameter_min: float | None = None
    parameter_max: float | None = None
    measured_min: float | None = None
    measured_max: float | None = None

    def __post_init__(self) -> None:
        self.samples = [
            sample if isinstance(sample, CalibrationSample) else CalibrationSample.from_dict(sample)
            for sample in self.samples
        ]
        if not self.samples:
            return

        parameter_values = [sample.parameter_value for sample in self.samples]
        measured_values = [sample.measured_value for sample in self.samples]
        if self.parameter_min is None:
            self.parameter_min = min(parameter_values)
        if self.parameter_max is None:
            self.parameter_max = max(parameter_values)
        if self.measured_min is None:
            self.measured_min = min(measured_values)
        if self.measured_max is None:
            self.measured_max = max(measured_values)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "CalibrationModel":
        return cls(
            samples=[CalibrationSample.from_dict(sample) for sample in data.get("samples", [])],
            fit_kind=str(data.get("fit_kind", "piecewise")),
            slope=float(data["slope"]) if data.get("slope") is not None else None,
            intercept=float(data["intercept"]) if data.get("intercept") is not None else None,
            max_abs_error=float(data["max_abs_error"]) if data.get("max_abs_error") is not None else None,
            rmse=float(data["rmse"]) if data.get("rmse") is not None else None,
            parameter_min=float(data["parameter_min"]) if data.get("parameter_min") is not None else None,
            parameter_max=float(data["parameter_max"]) if data.get("parameter_max") is not None else None,
            measured_min=float(data["measured_min"]) if data.get("measured_min") is not None else None,
            measured_max=float(data["measured_max"]) if data.get("measured_max") is not None else None,
        )

    @classmethod
    def fit(
        cls,
        samples: list[CalibrationSample],
    ) -> "CalibrationModel":
        if len(samples) < 2:
            raise ValueError("At least two calibration samples are required.")

        normalized_samples = [
            sample if isinstance(sample, CalibrationSample) else CalibrationSample.from_dict(sample)
            for sample in samples
        ]
        return cls(
            samples=normalized_samples,
            fit_kind="piecewise",
        )

    def predict_measured_value(self, parameter_value: float) -> float:
        if not self.samples:
            raise ValueError("Calibration model has no samples.")

        sorted_samples = sorted(self.samples, key=lambda sample: sample.parameter_value)
        clamped_value = _clamp(parameter_value, sorted_samples[0].parameter_value, sorted_samples[-1].parameter_value)
        for lower, upper in zip(sorted_samples, sorted_samples[1:], strict=True):
            if lower.parameter_value <= clamped_value <= upper.parameter_value:
                return _linear_interpolate(
                    lower.parameter_value,
                    lower.measured_value,
                    upper.parameter_value,
                    upper.measured_value,
                    clamped_value,
                )
        return sorted_samples[-1].measured_value

    def resolve_parameter_for_measurement(self, measured_value: float) -> float:
        if not self.samples:
            raise ValueError("Calibration model has no samples.")
        clamped_measured = _clamp(
            measured_value,
            self.measured_min if self.measured_min is not None else measured_value,
            self.measured_max if self.measured_max is not None else measured_value,
        )

        sorted_samples = sorted(self.samples, key=lambda sample: sample.measured_value)
        for lower, upper in zip(sorted_samples, sorted_samples[1:], strict=True):
            lower_value = lower.measured_value
            upper_value = upper.measured_value
            if lower_value <= clamped_measured <= upper_value or upper_value <= clamped_measured <= lower_value:
                return _linear_interpolate(
                    lower.measured_value,
                    lower.parameter_value,
                    upper.measured_value,
                    upper.parameter_value,
                    clamped_measured,
                )
        return sorted_samples[-1].parameter_value


@dataclass(slots=True, frozen=True)
class DiscoveredDevice:
    port: str
    description: str
    hwid: str


@dataclass(slots=True, frozen=True)
class DeviceInfo:
    port: str | None
    firmware: str
    nickname: str | None = None
    inferred_model: str | None = None
    status: str | None = None


@dataclass(slots=True, frozen=True)
class WorkspaceBounds:
    model: str
    width_mm: float
    height_mm: float

    @classmethod
    def from_file(cls, path: str | Path) -> "WorkspaceBounds":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**data)

    def to_file(self, path: str | Path) -> None:
        serialized = _drop_none_values(asdict(self))
        Path(path).write_text(json.dumps(serialized, indent=2) + "\n", encoding="utf-8")


NICKNAME_MODEL_ALIASES: dict[str, str] = {
    "V3A3": "v3a3",
    "SEA3": "v3a3",
    "V3XLX": "v3xlx",
    "XLX": "v3xlx",
    "MINIKIT": "minikit",
    "SEA1": "sea1",
    "SEA2": "sea2",
    "V3B6": "v3b6",
    "SEA0": "sea0",
    "A0": "sea0",
    "A1": "sea1",
    "A2": "sea2",
    "A3": "v3a3",
    "A4": "default",
}


DRAWCORE_WORKSPACE_PRESETS: dict[str, WorkspaceBounds] = {
    "default": WorkspaceBounds("default", 8.27 * MM_PER_INCH, 11.81 * MM_PER_INCH),
    "v3a3": WorkspaceBounds("v3a3", 11.69 * MM_PER_INCH, 16.93 * MM_PER_INCH),
    "v3xlx": WorkspaceBounds("v3xlx", 8.58 * MM_PER_INCH, 23.42 * MM_PER_INCH),
    "minikit": WorkspaceBounds("minikit", 4.00 * MM_PER_INCH, 6.30 * MM_PER_INCH),
    "sea1": WorkspaceBounds("sea1", 23.39 * MM_PER_INCH, 34.02 * MM_PER_INCH),
    "sea2": WorkspaceBounds("sea2", 17.01 * MM_PER_INCH, 23.39 * MM_PER_INCH),
    "v3b6": WorkspaceBounds("v3b6", 5.51 * MM_PER_INCH, 7.48 * MM_PER_INCH),
    "sea0": WorkspaceBounds("sea0", 33.11 * MM_PER_INCH, 46.85 * MM_PER_INCH),
}


def workspace_bounds_for_model(model: str) -> WorkspaceBounds:
    return DRAWCORE_WORKSPACE_PRESETS[model.lower()]


def infer_model_from_nickname(nickname: str | None) -> str | None:
    if not nickname:
        return None

    normalized = "".join(character for character in nickname.upper() if character.isalnum())
    if not normalized:
        return None

    for alias, model in sorted(NICKNAME_MODEL_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias in normalized:
            return model
    return None


@dataclass(slots=True)
class MotionConfig:
    feed_rate_xy: int = 1200
    feed_rate_pen_up: int = 5000
    feed_rate_pen_down: int = 5000
    pen_up_position: float = 0.5
    pen_down_position: float = 5.0
    line_width_calibration: CalibrationModel | None = None
    blot_delay_calibration: CalibrationModel | None = None

    def __post_init__(self) -> None:
        self.pen_up_position = clamp_pen_position(self.pen_up_position)
        self.pen_down_position = clamp_pen_position(self.pen_down_position)
        if self.line_width_calibration is not None and not isinstance(self.line_width_calibration, CalibrationModel):
            self.line_width_calibration = CalibrationModel.from_dict(self.line_width_calibration)
        if self.blot_delay_calibration is not None and not isinstance(self.blot_delay_calibration, CalibrationModel):
            self.blot_delay_calibration = CalibrationModel.from_dict(self.blot_delay_calibration)

    @classmethod
    def from_file(cls, path: str | Path) -> MotionConfig:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("line_width_calibration") is not None:
            data["line_width_calibration"] = CalibrationModel.from_dict(data["line_width_calibration"])
        if data.get("blot_delay_calibration") is not None:
            data["blot_delay_calibration"] = CalibrationModel.from_dict(data["blot_delay_calibration"])
        return cls(**data)

    def to_file(self, path: str | Path) -> None:
        serialized = _drop_none_values(asdict(self))
        Path(path).write_text(json.dumps(serialized, indent=2) + "\n", encoding="utf-8")

    def feed_rate_for_line_width(self, line_width_mm: float) -> int | None:
        if self.line_width_calibration is None:
            return None
        return round(self.line_width_calibration.resolve_parameter_for_measurement(line_width_mm))

    def blot_delay_for_size(self, blot_size_mm: float) -> int | None:
        if self.blot_delay_calibration is None:
            return None
        return round(self.blot_delay_calibration.resolve_parameter_for_measurement(blot_size_mm))
