"""Regression tests for the self-contained 310A1394 ice adapter."""

from unittest.mock import patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import Platform
from midea_ac_lan.ca_ice import (
    MideaCAIceDevice,
    build_ice_mode_body,
    build_ice_power_body,
)
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


def _status(
    message_type: MessageType = MessageType.query,
    ice_power: bool = False,
    rapid: bool = False,
) -> bytes:
    """Make a general CA status with ice and unrelated control bits set."""
    body = bytearray(78)
    body[0] = 2 if message_type == MessageType.notify1 else 0
    body[1] = 0x9C
    body[2] = 0x35
    body[3] = 5
    body[4] = 50
    body[7] = 0x30
    body[8] = 0x84 if ice_power else 0x04
    body[14] = 0x0F
    body[15] = 0x28
    body[17] = 110
    body[18] = 90
    body[19] = 100
    body[20] = 120
    body[44] = 0x20 if rapid else 0
    header = bytearray([0xAA] + [0] * 7 + [ProtocolVersion.V1, message_type])
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
    assert changes["ice_making_mode"] == "off"
    assert changes["freezer_icemaker_water_shortage"] is False


def test_ice_water_shortage_is_distinct_from_raw_water_status() -> None:
    """The shortage alert is bit 5, not the older valid/invalid bit 2."""
    device = _device()
    shortage = bytearray(_status(ice_power=True))
    shortage[10 + 14] = 0x20
    changes = device.process_message(bytes(shortage))
    assert changes["freezer_icemaker_water_shortage"] is True
    assert changes["freezing_ice_machine_water_status"] is False

    normal = bytearray(_status(ice_power=True))
    normal[10 + 14] = 0x04
    changes = device.process_message(bytes(normal))
    assert changes["freezer_icemaker_water_shortage"] is False
    assert changes["freezing_ice_machine_water_status"] is True


def test_ice_water_shortage_ignores_x02_notification() -> None:
    """An X02 notification must not overwrite the authoritative X00 alert."""
    device = _device()
    shortage = bytearray(_status(ice_power=True))
    shortage[10 + 14] = 0x20
    device.process_message(bytes(shortage))
    notification = device.process_message(_status(MessageType.notify1))
    assert "freezer_icemaker_water_shortage" not in notification
    assert device.get_attribute("freezer_icemaker_water_shortage") is True


def test_ice_mode_is_read_from_extended_status() -> None:
    """Power and quick ice bit together determine the displayed mode."""
    device = _device()
    assert (
        device.process_message(_status(ice_power=True))["ice_making_mode"] == "normal"
    )
    assert device.process_message(_status(ice_power=True, rapid=True))[
        "ice_making_mode"
    ] == "rapid"


def test_ice_mode_control_sets_power_and_quick_bit() -> None:
    """Each option changes only the ice power and quick ice control bits."""
    device = _device()
    device.process_message(_status(ice_power=True))
    for mode, expected_power, expected_quick in (
        ("off", 0, 0),
        ("normal", 0x80, 0),
        ("rapid", 0x80, 0x20),
    ):
        with patch.object(device, "build_send") as send:
            device.set_attribute("ice_making_mode", mode)
        body = send.call_args.args[0].body
        assert len(body) == 45
        assert body[8] & 0x80 == expected_power
        assert body[44] & 0x20 == expected_quick
        assert body[1] == EXPECTED_MODE


def test_ice_mode_rejects_short_status_and_unknown_option() -> None:
    """Do not send an extended command without a complete status."""
    with pytest.raises(ValueError, match="extended general status"):
        build_ice_mode_body(bytearray(40), "rapid")
    with pytest.raises(ValueError, match="Unsupported ice making mode"):
        build_ice_mode_body(bytearray(78), "other")


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


def test_notification_does_not_replace_control_ready_status() -> None:
    """An X02 notification may update flags but cannot seed an X00 write."""
    device = _device()
    device.process_message(_status())
    original_body = device._last_general_body
    device.process_message(_status(MessageType.notify1))
    assert device._last_general_body == original_body
    with patch.object(device, "build_send") as send:
        device.set_attribute("freezing_ice_machine_power", True)
    assert send.call_args.args[0].body[0] == 0


def test_notification_without_query_cannot_control() -> None:
    """Wait for an X00 status rather than using an X02 notification."""
    device = _device()
    device.process_message(_status(MessageType.notify1))
    with patch.object(device, "build_send") as send:
        with pytest.raises(ValueError, match="recent status"):
            device.set_attribute("freezing_ice_machine_power", True)
        send.assert_not_called()


def test_stale_notification_does_not_revert_ice_switch() -> None:
    """Wait for a query before accepting an old power bit after a set."""
    device = _device()
    device.process_message(_status())
    with patch.object(device, "build_send"):
        device.set_attribute("freezing_ice_machine_power", True)
    device.process_message(_status(MessageType.set, ice_power=True))
    assert device.get_attribute("freezing_ice_machine_power") is True

    changes = device.process_message(_status(MessageType.notify1))
    assert "freezing_ice_machine_power" not in changes
    assert device.get_attribute("freezing_ice_machine_power") is True

    device.process_message(_status(ice_power=True))
    assert device._pending_ice_power is None
    assert device.get_attribute("freezing_ice_machine_power") is True


def test_query_can_reject_unapplied_ice_command() -> None:
    """A later status query wins when the appliance did not apply a command."""
    device = _device()
    device.process_message(_status())
    with patch.object(device, "build_send"):
        device.set_attribute("freezing_ice_machine_power", True)
    device.process_message(_status(MessageType.set, ice_power=True))
    changes = device.process_message(_status())
    assert changes["freezing_ice_machine_power"] is False
    assert device._pending_ice_power is None


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
    assert "ice_making_mode" not in device.attributes
    assert "freezer_icemaker_water_shortage" not in device.attributes
    with patch.object(device, "build_send") as send:
        device.set_attribute("freezing_ice_machine_power", True)
        send.assert_not_called()


def test_new_status_entities_are_limited_to_310a1394() -> None:
    """Unknown CA models cannot create the extra flag sensors."""
    entities = MIDEA_DEVICES[0xCA]["entities"]
    for key in (
        "ice_making_mode",
        "freezer_icemaker_water_shortage",
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


def test_ice_water_shortage_is_a_translated_enum_sensor() -> None:
    """Map the two shortage bit values to human-readable sensor states."""
    entity = MIDEA_DEVICES[0xCA]["entities"]["freezer_icemaker_water_shortage"]
    assert entity["type"] == Platform.SENSOR
    assert entity["device_class"] == SensorDeviceClass.ENUM
    assert entity["options"] == {True: "abnormal", False: "normal"}


def test_short_status_is_rejected() -> None:
    """A partial status is never used to build a control frame."""
    with pytest.raises(ValueError, match="general status"):
        build_ice_power_body(bytearray([0]), True)
