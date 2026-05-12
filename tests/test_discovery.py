from pydrawcore.discovery import discover_devices


def test_discover_devices_filters_drawcore_ports(monkeypatch) -> None:
    class FakePort:
        def __init__(self, device: str, description: str, hwid: str) -> None:
            self.device = device
            self.description = description
            self.hwid = hwid

    monkeypatch.setattr(
        "pydrawcore.discovery.comports",
        lambda: [
            FakePort("COM4", "USB Serial Device (COM4)", "USB VID:PID=1A86:8040 SER=20191234 LOCATION=1-1"),
            FakePort("COM7", "Other Device", "USB VID:PID=1234:5678"),
        ],
    )

    devices = discover_devices()
    assert len(devices) == 1
    assert devices[0].port == "COM4"