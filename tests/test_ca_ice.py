"""Regression tests for the self-contained 310A1394 ice adapter."""

from unittest.mock import patch

import pytest
from midea_ac_lan.ca_ice import MideaCAIceDevice, build_ice_power_body
from midealan.const import ProtocolVersion
from midealan.message import MessageType

TEST_AUTH = "AA"
EXPECTED_BODY_LENGTH = 40
EXPECTED_MODE = 0x24
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
    body[1] = 0x24
    body[2] = 0x35
    body[3] = 5
    body[4] = 50
    body[7] = 0x30
    body[8] = 0x04
    body[14] = 0x0C
    body[15] = 0x08
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
    with patch.object(device, "build_send") as send:
        device.set_attribute("freezing_ice_machine_power", True)
        send.assert_not_called()


def test_short_status_is_rejected() -> None:
    """A partial status is never used to build a control frame."""
    with pytest.raises(ValueError, match="general status"):
        build_ice_power_body(bytearray([0]), True)
