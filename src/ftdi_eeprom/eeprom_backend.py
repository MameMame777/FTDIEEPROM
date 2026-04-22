from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class PrivateApiError(RuntimeError):
    """Raised when pyftdi private API expectations are not met."""


def get_user_area_offset(eeprom: Any) -> int:
    props = _require_private_attr(eeprom, "_PROPERTIES")
    if isinstance(props, Mapping):
        device_version = _require_private_attr(eeprom, "device_version")
        if device_version not in props:
            raise PrivateApiError(f"Unable to infer FT4232H User Area offset for device version: {device_version}")
        props = props[device_version]
    if hasattr(props, "user"):
        return int(props.user)
    if isinstance(props, (tuple, list)) and len(props) >= 2:
        return int(props[1])
    raise PrivateApiError("Unable to infer FT4232H User Area offset from _PROPERTIES")


def get_user_area_size(eeprom: Any, offset: int | None = None) -> int:
    if offset is None:
        offset = get_user_area_offset(eeprom)
    buffer = _require_buffer(eeprom)
    limit = len(buffer) - 2
    if offset >= limit:
        raise PrivateApiError("User Area offset points beyond the writable EEPROM range")
    return limit - offset


def read_user_area(eeprom: Any, offset: int, size: int) -> bytes:
    buffer = _require_buffer(eeprom)
    limit = len(buffer) - 2
    if offset < 0 or size < 0 or offset + size > limit:
        raise PrivateApiError("Requested User Area range exceeds EEPROM bounds")
    return bytes(buffer[offset : offset + size])


def sync_eeprom(eeprom: Any) -> None:
    sync = _require_private_attr(eeprom, "_sync_eeprom")
    sync()


def get_decoded_config(eeprom: Any) -> dict[str, Any]:
    sync_eeprom(eeprom)
    config = _require_private_attr(eeprom, "_config")
    if not isinstance(config, Mapping):
        raise PrivateApiError("pyftdi private _config map is not a mapping")
    return dict(config)


def decode_raw_image(eeprom: Any, image: bytes) -> bytes:
    buffer = _require_buffer(eeprom)
    if len(image) != len(buffer):
        raise PrivateApiError(
            f"Raw image length mismatch: expected {len(buffer)} bytes, got {len(image)} bytes"
        )
    buffer[:] = image
    compute_crc = _require_private_attr(eeprom, "_compute_crc")
    compute_crc(buffer, True)
    if not bool(_require_private_attr(eeprom, "_valid")):
        raise PrivateApiError("Loaded raw image is invalid (CRC mismatch)")
    decode = _require_private_attr(eeprom, "_decode_eeprom")
    decode()
    return bytes(buffer)


def write_user_area(eeprom: Any, offset: int, data: bytes, *, dry_run: bool = False) -> bytes:
    sync_eeprom(eeprom)
    buffer = _require_buffer(eeprom)
    writable_limit = len(buffer) - 2
    if offset < 0 or offset > writable_limit:
        raise PrivateApiError("User Area offset is outside the writable EEPROM range")
    if offset + len(data) > writable_limit:
        raise PrivateApiError("User Area payload exceeds the writable EEPROM range")

    end_offset = offset + len(data)
    buffer[offset:end_offset] = data

    update_crc = _require_private_attr(eeprom, "_update_crc")
    update_crc()
    if dry_run:
        return bytes(buffer)

    overwrite = _require_private_attr(_require_private_attr(eeprom, "_ftdi"), "overwrite_eeprom")
    overwrite(buffer, dry_run=False)
    return bytes(buffer)


def write_raw_image(eeprom: Any, image: bytes, *, dry_run: bool = False) -> bytes:
    buffer = _require_buffer(eeprom)
    if len(image) != len(buffer):
        raise PrivateApiError(
            f"Raw image length mismatch: expected {len(buffer)} bytes, got {len(image)} bytes"
        )
    if dry_run:
        return bytes(image)
    overwrite = _require_private_attr(_require_private_attr(eeprom, "_ftdi"), "overwrite_eeprom")
    overwrite(image, dry_run=False)
    return bytes(image)


def _require_private_attr(obj: Any, attribute: str) -> Any:
    if not hasattr(obj, attribute):
        raise PrivateApiError(f"pyftdi private API missing expected attribute: {attribute}")
    return getattr(obj, attribute)


def _require_buffer(eeprom: Any) -> bytearray:
    buffer = _require_private_attr(eeprom, "_eeprom")
    if not isinstance(buffer, bytearray):
        raise PrivateApiError("pyftdi private _eeprom buffer is not a bytearray")
    return buffer
