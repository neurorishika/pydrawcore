"""Public package exports for PyDrawCore.

Import from the package root when you want the supported high-level surface:
controller access, discovery, configuration dataclasses, and turtle program
parsing and execution helpers.
"""

from .controller import DrawCoreController
from .discovery import discover_devices
from .models import (
    CalibrationModel,
    CalibrationSample,
    DeviceInfo,
    DiscoveredDevice,
    MotionConfig,
    WorkspaceBounds,
    infer_model_from_nickname,
    workspace_bounds_for_model,
)
from .program import Program, ProgramError, ProgramPreview, ProgramRunner, export_preview_svg, parse_program, preview_program, run_program

__all__ = [
    "CalibrationModel",
    "CalibrationSample",
    "DeviceInfo",
    "DiscoveredDevice",
    "MotionConfig",
    "WorkspaceBounds",
    "Program",
    "ProgramError",
    "ProgramPreview",
    "ProgramRunner",
    "DrawCoreController",
    "discover_devices",
    "export_preview_svg",
    "infer_model_from_nickname",
    "parse_program",
    "preview_program",
    "run_program",
    "workspace_bounds_for_model",
]
