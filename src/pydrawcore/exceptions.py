class PyDrawCoreError(Exception):
    """Base exception for the pydrawcore package."""


class ConnectionError(PyDrawCoreError):
    """Raised when a DrawCore device cannot be opened or identified."""


class ProtocolError(PyDrawCoreError):
    """Raised when the controller responds unexpectedly."""


class DeviceNotReadyError(PyDrawCoreError):
    """Raised when an operation requires an open serial transport."""
