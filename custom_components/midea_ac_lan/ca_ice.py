"""Local CA ice maker support for the 310A1394 refrigerator.

This adapter keeps the integration installable with the pinned midea-lan release.
The protocol implementation is also maintained in the companion midea-lan fork.
"""

import time
from typing import Any, Unpack

from midealan.const import DeviceType
from midealan.device import MideaDeviceInitKwargs
from midealan.devices import ca
from midealan.devices.ca.message import MessageCAResponse
from midealan.message import ListTypes, MessageQuestCustom, MessageType

MODEL = "310A1394"
SUBTYPE = 56
MAX_STATUS_AGE = 120
PENDING_ICE_POWER_AGE = 45
CONTROL_BODY_LENGTH = 40
MODE_CONTROL_BODY_LENGTH = 45
MIN_GENERAL_STATUS_LENGTH = 25
ICE_POWER_OFFSET = 8
ICE_POWER_MASK = 0x80
QUICK_ICE_OFFSET = 44
QUICK_ICE_MASK = 0x20
ICE_WATER_STATUS_OFFSET = 14
ICE_WATER_SHORTAGE_MASK = 0x20
ICE_MODES = ("off", "normal", "rapid")
STATUS_FLAGS = (
    "iced_mode",
    "freezing_ice_machine_power",
    "ice_mouth_power",
    "freezing_ice_machine_water_status",
    "freezing_all_ice_status",
    "storage_iceHome_door_state",
    "freezing_motor_deicing_status",
    "freezing_motor_reset_status",
    "smart_mode",
    "energy_saving_mode",
    "holiday_mode",
    "acme_freezing_mode",
)
CONTROL_STATUS_OFFSETS = (
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    16,
    25,
    27,
    28,
    29,
    30,
    31,
    33,
    35,
    36,
    37,
    38,
    39,
)
CONTROL_STATUS_MASKS = {
    6: 0xFD,
    7: 0xDF,
    16: 0xFE,
    25: 0x0F,
    33: 0x81,
    38: 0x01,
}
MODE_STATUS_MASKS = {40: 0x3D, 41: 0x08, 42: 0x3F, 43: 0xFF, 44: 0xF8}


def build_ice_power_body(status_body: bytearray, power: bool) -> bytearray:
    """Build the CA full control body, preserving current control fields.

    Returns
    -------
    bytearray
        Full CA control body.

    Raises
    ------
    ValueError
        If the latest status is not a complete CA general status.

    """
    if len(status_body) < MIN_GENERAL_STATUS_LENGTH or status_body[0] != ListTypes.X00:
        raise ValueError("A CA general status is required before control")
    body = bytearray(CONTROL_BODY_LENGTH)
    for offset in CONTROL_STATUS_OFFSETS:
        if offset < len(status_body):
            body[offset] = status_body[offset] & CONTROL_STATUS_MASKS.get(
                offset,
                0xFF,
            )
    body[ICE_POWER_OFFSET] = (
        body[ICE_POWER_OFFSET] | ICE_POWER_MASK
        if power
        else body[ICE_POWER_OFFSET] & ~ICE_POWER_MASK
    )
    return body


def build_ice_mode_body(status_body: bytearray, mode: str) -> bytearray:
    """Build the extended CA control body for off, normal, or rapid ice."""
    if mode not in ICE_MODES:
        raise ValueError(f"Unsupported ice making mode: {mode}")
    if len(status_body) < MODE_CONTROL_BODY_LENGTH or status_body[0] != ListTypes.X00:
        raise ValueError(
            "A CA extended general status is required before ice mode control"
        )
    body = build_ice_power_body(status_body, mode != "off")
    body.extend(bytearray(MODE_CONTROL_BODY_LENGTH - len(body)))
    for offset, mask in MODE_STATUS_MASKS.items():
        body[offset] = status_body[offset] & mask
    body[QUICK_ICE_OFFSET] = (
        body[QUICK_ICE_OFFSET] | QUICK_ICE_MASK
        if mode == "rapid"
        else body[QUICK_ICE_OFFSET] & ~QUICK_ICE_MASK
    )
    return body


class MideaCAIceDevice(ca.MideaCADevice):
    """Add ice status and guarded power control to one refrigerator model."""

    def __init__(
        self,
        *,
        customize: str,
        **kwargs: Unpack[MideaDeviceInitKwargs],
    ) -> None:
        """Initialize the CA device with optional ice status fields."""
        super().__init__(customize=customize, **kwargs)
        self._last_general_body: bytearray | None = None
        self._last_general_status_at: float | None = None
        self._pending_ice_power: bool | None = None
        self._pending_ice_power_until: float | None = None
        self._pending_ice_mode: str | None = None
        self._pending_ice_mode_until: float | None = None
        if self.model == MODEL and self.subtype == SUBTYPE:
            for key in STATUS_FLAGS:
                self._attributes[key] = None
            self._attributes["ice_making_mode"] = None
            self._attributes["freezer_icemaker_water_shortage"] = None

    def process_message(self, msg: bytes) -> dict[str, Any]:
        """Normalize the parser's ice bit masks to booleans.

        Returns
        -------
        dict[str, Any]
            Changed device attributes.

        """
        if self.model != MODEL or self.subtype != SUBTYPE:
            return super().process_message(msg)
        previous_ice_power = self._attributes.get("freezing_ice_machine_power")
        new_status = super().process_message(msg)
        message = MessageCAResponse(msg)
        if hasattr(message, "freezing_ice_machine_power"):
            # An X02 notification carries ice flags but cannot seed the X00
            # control body. Keep the latest control-ready X00 status.
            if (
                len(message.body) >= MIN_GENERAL_STATUS_LENGTH
                and message.body[0] == ListTypes.X00
            ):
                self._last_general_body = bytearray(message.body)
                self._last_general_status_at = time.monotonic()
            if self._pending_ice_power is not None and (
                message.message_type == MessageType.query
                or self._pending_ice_power_until is None
                or time.monotonic() >= self._pending_ice_power_until
            ):
                # A fresh query confirms or rejects the command. Notifications
                # immediately following a set can still contain the old bit.
                self._pending_ice_power = None
                self._pending_ice_power_until = None
            for key in STATUS_FLAGS:
                value = bool(getattr(message, key))
                if (
                    key == "freezing_ice_machine_power"
                    and self._pending_ice_power is not None
                    and value != self._pending_ice_power
                    and message.message_type in (MessageType.set, MessageType.notify1)
                ):
                    self._attributes[key] = previous_ice_power
                    new_status.pop(key, None)
                    continue
                self._attributes[key] = value
                new_status[key] = value
            if (
                message.message_type == MessageType.query
                and len(message.body) > ICE_WATER_STATUS_OFFSET
                and message.body[0] == ListTypes.X00
            ):
                # The raw water status at bit 2 means valid/invalid. The
                # separate bit 5 is the actual ice maker shortage signal.
                shortage = bool(
                    message.body[ICE_WATER_STATUS_OFFSET] & ICE_WATER_SHORTAGE_MASK
                )
                self._attributes["freezer_icemaker_water_shortage"] = shortage
                new_status["freezer_icemaker_water_shortage"] = shortage
            if (
                message.message_type in (MessageType.query, MessageType.set)
                and len(message.body) >= MODE_CONTROL_BODY_LENGTH
                and message.body[0] == ListTypes.X00
            ):
                mode = (
                    "off"
                    if not bool(message.body[ICE_POWER_OFFSET] & ICE_POWER_MASK)
                    else (
                        "rapid"
                        if message.body[QUICK_ICE_OFFSET] & QUICK_ICE_MASK
                        else "normal"
                    )
                )
                if self._pending_ice_mode is not None:
                    if message.message_type == MessageType.query or (
                        self._pending_ice_mode_until is not None
                        and time.monotonic() >= self._pending_ice_mode_until
                    ):
                        self._pending_ice_mode = None
                        self._pending_ice_mode_until = None
                    elif mode != self._pending_ice_mode:
                        return new_status
                self._attributes["ice_making_mode"] = mode
                new_status["ice_making_mode"] = mode
        return new_status

    def set_attribute(self, attr: str, value: bool | float | str) -> None:
        """Write only the ice maker power bit for the verified model.

        Raises
        ------
        TypeError
            If the requested power state is not a boolean.
        ValueError
            If no recent complete refrigerator status is available.

        """
        if self.model != MODEL or self.subtype != SUBTYPE or attr not in (
            "freezing_ice_machine_power", "ice_making_mode"
        ):
            return super().set_attribute(attr, value)
        if attr == "freezing_ice_machine_power" and not isinstance(value, bool):
            raise TypeError("Ice maker power must be a boolean")
        if (
            self._last_general_body is None
            or self._last_general_status_at is None
            or time.monotonic() - self._last_general_status_at > MAX_STATUS_AGE
        ):
            raise ValueError("Cannot set ice maker power without recent status")
        if attr == "ice_making_mode":
            if not isinstance(value, str):
                raise TypeError("Ice making mode must be a string")
            body = build_ice_mode_body(self._last_general_body, value)
            self._pending_ice_mode = value
            self._pending_ice_mode_until = time.monotonic() + PENDING_ICE_POWER_AGE
            self._pending_ice_power = value != "off"
        else:
            body = build_ice_power_body(self._last_general_body, value)
            self._pending_ice_power = value
        self._pending_ice_power_until = time.monotonic() + PENDING_ICE_POWER_AGE
        try:
            self.build_send(
                MessageQuestCustom(
                    DeviceType.CA,
                    self._message_protocol_version,
                    MessageType.set,
                    body,
                ),
            )
        except Exception:
            self._pending_ice_power = None
            self._pending_ice_power_until = None
            self._pending_ice_mode = None
            self._pending_ice_mode_until = None
            raise
        return None


def install_ca_ice_adapter() -> None:
    """Use the local CA subclass for devices selected by midea-lan."""
    ca.MideaAppliance = MideaCAIceDevice
