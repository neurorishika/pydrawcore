from __future__ import annotations

from .exceptions import ProtocolError


def ensure_cr(command: str) -> str:
    normalized = command.strip()
    if not normalized:
        raise ProtocolError("Command cannot be empty.")
    if normalized.endswith("\r"):
        return normalized
    return f"{normalized}\r"


def parse_ok(response: str, command: str) -> None:
    if response.strip().lower().startswith("ok"):
        return
    raise ProtocolError(f"Unexpected response for command {command!r}: {response!r}")


def parse_version(response: str) -> str:
    text = response.strip()
    if not text.startswith("DrawCore"):
        raise ProtocolError(f"Unexpected version response: {response!r}")
    return text
