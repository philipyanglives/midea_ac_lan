"""Regression tests for the self-contained 310A1394 ice adapter."""

from unittest.mock import patch

import pytest
from midea_ac_lan.ca_ice import MideaCAIceDevice, build_ice_power_body
from midea_ac_lan.const import supports_device
from midea_ac_lan.midea_devices import MIDEA_DEVICES
from midealan.const import ProtocolVersion
from midealan.message import MessageType

TEST_AUTH = "AA"
EXPECTED_BODY_LENGTH = 40
EXPECTED_MODE = 0x9C
EXPECTED_OTHER = 0x10
EXPECTED_ICE_ON = 0x84


def _device(model: str = "310A1394") -> MideaCAIceDevice:
    """Create an offline refrigerator with test-only credentials."""
    return MideaCAIceDevice(
        name="Test Refrigerator",
        device_id=1,
        ip_address="127.0.0.1",
        port=6444,
        token=TEST_AUTH,
        key="BB",
        device_protocol=ProtocolVersion.V1,
        model=model,
        subtype=56,
        customize="",
    )


def _status() -> bytes:
    """Make a general CA status with ice and unrelated control bits set."""
    body = bytearray(32)
    body[0] = 0
    body[1] = 0x9C
    body[2] = 0x35
    body[3] = 5
    body[4] = 50
    body[7] = 0x30
    body[8] = 0x04
    body[14] = 0x0F
    body[15] = 0x28
    body[17] = 110
    body[18] = 90
    body[19] = 100
    body[20] = 120
    header = bytearray([0xAA] + [0] * 7 + [ProtocolVersion.V1, MessageType.query])
    return bytes(header + body + bytearray([0]))


def test_status_bits_are_boolean() -> None:
    """The existing parser's bit masks become HA-compatible boolean states."""
    device = _device()
    changes = device.process_message(_status())
    assert changes["iced_mode"] is True
    assert changes["freezing_ice_machine_power"] is False
    assert changes["freezing_all_ice_status"] is True
    assert changes["freezing_ice_machine_water_status"] is True
    assert changes["ice_mouth_power"] is True
    assert changes["storage_iceHome_door_state"] is True
    assert changes["freezing_motor_deicing_status"] is True
    assert changes["freezing_motor_reset_status"] is True
    assert changes["smart_mode"] is True
    assert changes["energy_saving_mode"] is True
    assert changes["holiday_mode"] is True
    assert changes["acme_freezing_mode"] is True


def test_control_changes_only_power_bit() -> None:
    """The 40-byte control body preserves current mode bits and masks reserved bits."""
    device = _device()
    device.process_message(_status())
    with patch.object(device, "build_send") as send:
        device.set_attribute("freezing_ice_machine_power", True)
    command = send.call_args.args[0]
    assert len(command.body) == EXPECTED_BODY_LENGTH
    assert command.message_type == MessageType.set
    assert command.body[1] == EXPECTED_MODE
    assert command.body[7] == EXPECTED_OTHER
    assert command.body[8] == EXPECTED_ICE_ON
    assert device.get_attribute("freezing_ice_machine_power") is False


def test_requires_recent_status() -> None:
    """Control never sends a command without a recent general report."""
    device = _device()
    with patch.object(device, "build_send") as send:
        with pytest.raises(ValueError, match="recent status"):
            device.set_attribute("freezing_ice_machine_power", True)
        send.assert_not_called()
    device.process_message(_status())
    device._last_general_status_at = 0
    with patch.object(device, "build_send") as send:
        with pytest.raises(ValueError, match="recent status"):
            device.set_attribute("freezing_ice_machine_power", True)
        send.assert_not_called()


def test_invalid_power_type_is_rejected() -> None:
    """A service caller cannot turn a non-empty string into an on command."""
    device = _device()
    device.process_message(_status())
    with patch.object(device, "build_send") as send:
        with pytest.raises(TypeError, match="boolean"):
            device.set_attribute("freezing_ice_machine_power", "false")
        send.assert_not_called()


def test_other_model_keeps_upstream_behavior() -> None:
    """An unrelated CA refrigerator never receives ice attributes or writes."""
    device = _device(model="other")
    assert "iced_mode" not in device.attributes
    assert "storage_iceHome_door_state" not in device.attributes
    with patch.object(device, "build_send") as send:
        device.set_attribute("freezing_ice_machine_power", True)
        send.assert_not_called()


def test_new_status_entities_are_limited_to_310a1394() -> None:
    """Unknown CA models cannot create the extra flag sensors."""
    entities = MIDEA_DEVICES[0xCA]["entities"]
    for key in (
        "storage_iceHome_door_state",
        "freezing_motor_deicing_status",
        "freezing_motor_reset_status",
        "smart_mode",
        "energy_saving_mode",
        "holiday_mode",
        "acme_freezing_mode",
    ):
        assert supports_device("310A1394", 56, entities[key])
        assert not supports_device("other", 56, entities[key])
        assert not supports_device("310A1394", 21, entities[key])


def test_short_status_is_rejected() -> None:
    """A partial status is never used to build a control frame."""
    with pytest.raises(ValueError, match="general status"):
        build_ice_power_body(bytearray([0]), True)
