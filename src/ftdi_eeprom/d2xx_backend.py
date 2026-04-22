from __future__ import annotations

import ctypes as c
from dataclasses import dataclass
from importlib import import_module
import re
from typing import Any, Mapping


FT4232H_DEVICE_VERSION = 0x0800
FT4232H_D2XX_TYPE = 7
FT4232H_EEPROM_SIZE = 0x100
CHANNEL_LETTERS = {1: "A", 2: "B", 3: "C", 4: "D"}
CHANNEL_INDEX = {letter: index for index, letter in CHANNEL_LETTERS.items()}


@dataclass(frozen=True)
class D2xxDescriptor:
    base_serial: str
    actual_serial: str
    description: str
    interface: int | None


def list_devices(vendor_id: int, product_id: int, serial: str | None = None) -> list[dict[str, str | None]]:
    grouped: dict[str, D2xxDescriptor] = {}
    for descriptor in _enumerate_descriptors(vendor_id, product_id):
        if serial and not _serial_matches(serial, descriptor):
            continue
        grouped.setdefault(descriptor.base_serial, descriptor)
    return [
        {"serial": base_serial or None, "description": _strip_channel_suffix(descriptor.description)}
        for base_serial, descriptor in grouped.items()
    ]


def open_eeprom(url: str, vendor_id: int, product_id: int, chip_name: str) -> Any:
    ftd2xx = _import_ftd2xx()
    descriptor = _resolve_descriptor(url, vendor_id, product_id, chip_name)
    handle = ftd2xx.openEx(
        descriptor.actual_serial.encode("ascii"),
        int(ftd2xx.defines.OpenExFlags.OPEN_BY_SERIAL_NUMBER),
        update=False,
    )
    try:
        device_info = handle.getDeviceInfo()
        if int(device_info["type"]) != FT4232H_D2XX_TYPE:
            raise RuntimeError("Connected FTDI device is not an FT4232H")
        FtdiEeprom = import_module("pyftdi.eeprom").FtdiEeprom
        eeprom = FtdiEeprom()
        eeprom.connect(_D2xxFtdiAdapter(handle))
        return eeprom
    except Exception:
        handle.close()
        raise


def program_eeprom(eeprom: Any, config: Mapping[str, Any], user_area_payload: bytes) -> None:
    _program_handle(_require_handle(eeprom), _build_settings_from_config(config), user_area_payload)


def program_decoded_eeprom(
    eeprom: Any,
    decoded_config: Mapping[str, Any],
    user_area_payload: bytes | None = None,
) -> None:
    _program_handle(_require_handle(eeprom), decoded_config, user_area_payload)


def restore_eeprom(
    eeprom: Any,
    decoded_config: Mapping[str, Any],
    image: bytes,
    user_area_offset: int,
) -> None:
    handle = _require_handle(eeprom)
    user_area_size = int(handle.eeUASize())
    if user_area_offset < 0 or user_area_offset + user_area_size > len(image):
        raise RuntimeError("Raw image does not contain the full D2XX User Area payload")
    user_area_payload = image[user_area_offset : user_area_offset + user_area_size]
    _program_handle(handle, decoded_config, user_area_payload)


def _program_handle(handle: Any, settings: Mapping[str, Any], user_area_payload: bytes | None) -> None:
    progdata = handle.eeRead()
    _apply_settings_to_progdata(progdata, settings)
    handle.eeProgram(progdata)
    if user_area_payload is not None and len(user_area_payload) > 0:
        handle.eeUAWrite(user_area_payload)


def _apply_settings_to_progdata(progdata: Any, settings: Mapping[str, Any]) -> None:
    serial_enabled = bool(settings.get("has_serial", True))
    serial_number = str(settings.get("serial", "")).strip().encode("utf-8") if serial_enabled else b""

    progdata.VendorId = int(settings["vendor_id"])
    progdata.ProductId = int(settings["product_id"])
    progdata.Manufacturer = str(settings["manufacturer"]).encode("utf-8")
    progdata.Description = str(settings["product"]).encode("utf-8")
    progdata.SerialNumber = serial_number
    progdata.MaxPower = int(settings["power_max"])
    progdata.PnP = int(bool(settings.get("pnp", True)))
    _set_optional_attr(progdata, "SerNumEnable8", int(serial_enabled))
    _set_optional_attr(progdata, "SelfPowered", int(bool(settings.get("self_powered", False))))
    _set_optional_attr(progdata, "RemoteWakeup", int(bool(settings.get("remote_wakeup", False))))
    _set_optional_attr(progdata, "PullDownEnable8", int(bool(settings.get("suspend_pull_down", False))))
    _set_optional_attr(progdata, "PowerSaveEnable", int(bool(settings.get("powersave", False))))

    for group_index, channel_letter in CHANNEL_LETTERS.items():
        group_key = group_index - 1
        prefix = channel_letter.lower()
        driver = str(settings[f"channel_{prefix}_driver"]).upper()
        channel_type = str(settings.get(f"channel_{prefix}_type", "UART")).upper()
        _set_optional_attr(progdata, f"{channel_letter}DriveCurrent", int(settings[f"group_{group_key}_drive"]))
        _set_optional_attr(progdata, f"{channel_letter}IsVCP8", int(driver == "VCP"))
        _set_optional_attr(progdata, f"{channel_letter}SlowSlew", int(bool(settings.get(f"group_{group_key}_slow_slew", False))))
        _set_optional_attr(progdata, f"{channel_letter}SchmittInput", int(bool(settings.get(f"group_{group_key}_schmitt", False))))
        _set_optional_attr(progdata, f"{channel_letter}RIIsTXDEN", int(channel_type == "RS485"))


def _build_settings_from_config(config: Mapping[str, Any]) -> dict[str, Any]:
    device = config["device"]
    channels = config["channels"]
    settings: dict[str, Any] = {
        "vendor_id": device["vendor_id"],
        "product_id": device["product_id"],
        "manufacturer": device["manufacturer"],
        "product": device["product"],
        "serial": device.get("serial", ""),
        "power_max": device["power_max"],
        "has_serial": bool(device.get("has_serial", True)),
        "pnp": bool(device.get("pnp", True)),
        "self_powered": bool(device.get("self_powered", False)),
        "remote_wakeup": bool(device.get("remote_wakeup", False)),
        "suspend_pull_down": bool(device.get("suspend_pull_down", False)),
    }
    for group_index, channel_letter in CHANNEL_LETTERS.items():
        channel = channels[channel_letter]
        prefix = channel_letter.lower()
        settings[f"channel_{prefix}_driver"] = channel["driver"]
        settings[f"channel_{prefix}_type"] = channel.get("type", "UART")
        settings[f"group_{group_index - 1}_drive"] = channel["drive_current_ma"]
        settings[f"group_{group_index - 1}_slow_slew"] = bool(channel.get("slow_slew", False))
        settings[f"group_{group_index - 1}_schmitt"] = bool(channel.get("schmitt", False))
    return settings


def _set_optional_attr(target: Any, attribute: str, value: Any) -> None:
    if hasattr(target, attribute):
        setattr(target, attribute, value)


def _resolve_descriptor(url: str, vendor_id: int, product_id: int, chip_name: str) -> D2xxDescriptor:
    requested_serial, interface = _parse_url(url, chip_name)
    descriptors = _enumerate_descriptors(vendor_id, product_id)
    if requested_serial is None:
        base_serials = sorted({descriptor.base_serial for descriptor in descriptors})
        if len(base_serials) != 1:
            raise RuntimeError("D2XX URL resolution requires a unique FT4232H device selection")
        requested_serial = base_serials[0]
    matches = [
        descriptor
        for descriptor in descriptors
        if _serial_matches(requested_serial, descriptor) and descriptor.interface == interface
    ]
    if not matches:
        raise RuntimeError(f"No FT4232H interface matched serial={requested_serial!r} interface={interface}")
    return matches[0]


def _parse_url(url: str, chip_name: str) -> tuple[str | None, int]:
    ftdi_match = re.match(rf"^ftdi://ftdi:{re.escape(chip_name)}(?::([^/]+))?/([1-4])$", url)
    if ftdi_match:
        serial, interface = ftdi_match.groups()
        return serial, int(interface)
    d2xx_match = re.match(r"^ftd2xx://([^/]+)?/([1-4])$", url)
    if d2xx_match:
        serial, interface = d2xx_match.groups()
        return serial or None, int(interface)
    raise RuntimeError(f"Unsupported FTDI URL for Windows D2XX backend: {url}")


def _enumerate_descriptors(vendor_id: int, product_id: int) -> list[D2xxDescriptor]:
    ftd2xx = _import_ftd2xx()
    device_count = int(ftd2xx.createDeviceInfoList())
    descriptors: list[D2xxDescriptor] = []
    for index in range(device_count):
        detail = ftd2xx.getDeviceInfoDetail(index, update=False)
        device_id = int(detail["id"])
        if (device_id >> 16) != vendor_id or (device_id & 0xFFFF) != product_id:
            continue
        actual_serial = _decode_bytes(detail["serial"])
        description = _decode_bytes(detail["description"])
        base_serial, interface = _split_serial_and_interface(actual_serial, description)
        descriptors.append(
            D2xxDescriptor(
                base_serial=base_serial,
                actual_serial=actual_serial,
                description=description,
                interface=interface,
            )
        )
    return descriptors


def _split_serial_and_interface(actual_serial: str, description: str) -> tuple[str, int | None]:
    serial_channel = actual_serial[-1] if actual_serial and actual_serial[-1] in CHANNEL_INDEX else None
    description_match = re.search(r"\b([ABCD])$", description)
    description_channel = description_match.group(1) if description_match else None
    if serial_channel and (description_channel is None or description_channel == serial_channel):
        return actual_serial[:-1], CHANNEL_INDEX[serial_channel]
    if description_channel:
        return actual_serial, CHANNEL_INDEX[description_channel]
    return actual_serial, None


def _serial_matches(requested_serial: str, descriptor: D2xxDescriptor) -> bool:
    return requested_serial in {descriptor.base_serial, descriptor.actual_serial}


def _strip_channel_suffix(description: str) -> str:
    return re.sub(r"\s+[ABCD]$", "", description)


def _decode_bytes(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return value.decode("ascii", errors="ignore")
    return value


def _import_ftd2xx() -> Any:
    return import_module("ftd2xx")


def _require_handle(eeprom: Any) -> Any:
    ftdi = getattr(eeprom, "_ftdi", None)
    handle = getattr(ftdi, "_handle", None)
    if handle is None:
        raise RuntimeError("Windows D2XX EEPROM programming requires an open D2XX handle")
    return handle


class _D2xxFtdiAdapter:
    def __init__(self, handle: Any) -> None:
        self._handle = handle
        self._low_level = import_module("ftd2xx._ftd2xx")
        self._high_level = import_module("ftd2xx.ftd2xx")
        self._connected = True

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def device_version(self) -> int:
        return FT4232H_DEVICE_VERSION

    @property
    def is_eeprom_internal(self) -> bool:
        return False

    @property
    def max_eeprom_size(self) -> int:
        return FT4232H_EEPROM_SIZE

    def calc_eeprom_checksum(self, data: bytes | bytearray) -> int:
        checksum = 0xAAAA
        for offset in range(0, len(data), 2):
            value = ((data[offset + 1] << 8) + data[offset]) & 0xFFFF
            checksum = value ^ checksum
            checksum = ((checksum << 1) & 0xFFFF) | ((checksum >> 15) & 0xFFFF)
        return checksum

    def read_eeprom(self, addr: int = 0, length: int | None = None, eeprom_size: int | None = None) -> bytes:
        if addr % 2:
            raise ValueError("EEPROM read address must be word-aligned")
        total_size = eeprom_size or self.max_eeprom_size
        byte_length = total_size - addr if length is None else length
        if byte_length % 2:
            raise ValueError("EEPROM read length must be even")
        data = bytearray()
        start_word = addr // 2
        word_count = byte_length // 2
        for word_offset in range(word_count):
            value = c.c_ushort()
            self._high_level.call_ft(
                self._low_level.FT_ReadEE,
                self._handle.handle,
                start_word + word_offset,
                c.byref(value),
            )
            data.extend(int(value.value).to_bytes(2, "little"))
        return bytes(data)

    def overwrite_eeprom(self, image: bytes | bytearray, dry_run: bool = False) -> None:
        if len(image) != self.max_eeprom_size:
            raise ValueError(f"Raw image length mismatch: expected {self.max_eeprom_size} bytes, got {len(image)} bytes")
        if dry_run:
            return
        for address in range(0, len(image), 2):
            value = int.from_bytes(image[address : address + 2], "little")
            self._high_level.call_ft(
                self._low_level.FT_WriteEE,
                self._handle.handle,
                address // 2,
                c.c_ushort(value),
            )

    def close(self) -> None:
        if self._connected:
            try:
                self._handle.close()
            except Exception:
                pass
            self._connected = False

    def reset(self, usb_reset: bool = True) -> None:
        del usb_reset
        for method_name in ("cyclePort", "resetDevice", "resetPort"):
            method = getattr(self._handle, method_name, None)
            if callable(method):
                method()
                return