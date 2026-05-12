import pytest

from pydrawcore.exceptions import ProtocolError
from pydrawcore.protocol import ensure_cr, parse_ok, parse_version


def test_ensure_cr_appends_carriage_return() -> None:
    assert ensure_cr("V") == "V\r"
    assert ensure_cr("V\r") == "V\r"


def test_parse_ok_accepts_lowercase_ok() -> None:
    parse_ok("ok\n", "G1")


def test_parse_version_accepts_drawcore_response() -> None:
    assert parse_version("DrawCore V2.22.20260207\n") == "DrawCore V2.22.20260207"


def test_invalid_version_raises() -> None:
    with pytest.raises(ProtocolError):
        parse_version("nonsense")
