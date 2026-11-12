"""Offline checks for optional AC countdown and defrost entities."""

from unittest.mock import patch

from midea_ac_lan.midea_devices import MIDEA_DEVICES
from midea_ac_lan.number import MideaNumber
from midealan.const import ProtocolVersion
from midealan.devices.ac import DeviceAttributes as ACAttributes
from midealan.devices.ac import MideaACDevice


def test_timer_entities_are_optional_and_follow_reported_values() -> None:
    """A countdown is writable only when its reported value is present."""
    entities = MIDEA_DEVICES[0xAC]["entities"]
    for attr in (ACAttributes.power_on_timer, ACAttributes.power_off_timer):
        config = entities[attr]
        assert config["min"] == 0
        assert config["max"] == 1919
        assert config["available_value_attribute"] == attr
        assert not config.get("default", False)


def test_timer_number_requires_report_and_passes_minutes_to_library() -> None:
    """The HA number exposes a reported timer and forwards the requested duration."""
    device = MideaACDevice(
        name="Test AC",
        device_id=2,
        ip_address="127.0.0.1",
        port=6444,
        token="AA",
        key="BB",
        device_protocol=ProtocolVersion.V1,
        model="22012875",
        subtype=44204,
        customize="",
    )
    device.set_available()
    number = MideaNumber(device, ACAttributes.power_off_timer)
    assert not number.available
    with patch.object(device, "get_attribute", return_value=45):
        assert number.available
        assert number.native_value == 45
    with patch.object(device, "set_attribute") as send:
        number.set_native_value(30)
    send.assert_called_once_with(ACAttributes.power_off_timer, 30)


def test_defrost_status_is_optional_and_read_only() -> None:
    """An unreported diagnostic cannot show a fabricated off state."""
    config = MIDEA_DEVICES[0xAC]["entities"][ACAttributes.defrosting]
    assert config["available_value_attribute"] == ACAttributes.defrosting
    assert not config.get("default", False)
