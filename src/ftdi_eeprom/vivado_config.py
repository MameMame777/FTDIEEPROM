from __future__ import annotations

import struct
from typing import Any, Mapping

from .config_loader import get_default_config, merge_config

VIVADO_FIRMWARE_ID = 0x584A0004

FT4232H_HEADER_BYTES = 0x1A
EEPROM_CRC_BYTES = 2
STRING_TERMINATOR_BYTES = 2


def build_vivado_preset() -> dict[str, Any]:
    config = merge_config(
        get_default_config(),
        {
            "device": {
                "manufacturer": "Xilinx",
                "product": "FT4232H Vivado Bridge",
                "power_max": 100,
                "has_serial": True,
                "pnp": True,
            },
            "channels": {
                "A": {"driver": "D2XX", "type": "UART", "drive_current_ma": 4},
                "B": {"driver": "VCP", "type": "UART", "drive_current_ma": 4},
                "C": {"driver": "VCP", "type": "UART", "drive_current_ma": 4},
                "D": {"driver": "VCP", "type": "UART", "drive_current_ma": 4},
            },
            "vivado": {
                "enabled": True,
                "firmware_id": VIVADO_FIRMWARE_ID,
                "user_area": {
                    "vendor": "Xilinx",
                    "product": "FT4232H JTAG",
                },
            },
            "udev": {
                "group": "FPGAuser",
                "mode": "0660",
                "script_path": "/usr/local/bin/ftdi-unbind.sh",
                "unbind_interfaces": ["00", "01", "02", "03"],
            },
        },
    )
    config.pop("runtime_profile", None)
    return config


def has_vivado_payload(config: Mapping[str, Any]) -> bool:
    vivado = config.get("vivado")
    return bool(isinstance(vivado, Mapping) and vivado.get("enabled", False))


def build_user_area_payload(config: Mapping[str, Any]) -> bytes:
    vivado = config.get("vivado", {})
    user_area = vivado.get("user_area", {})
    vendor = str(user_area.get("vendor") or config["device"]["manufacturer"])
    product = str(user_area.get("product") or config["device"]["product"])
    firmware_id = int(vivado.get("firmware_id", VIVADO_FIRMWARE_ID))
    return struct.pack("<I", firmware_id) + vendor.encode("utf-8") + b"\x00" + product.encode("utf-8") + b"\x00"


def compute_string_descriptor_bytes(device: Mapping[str, Any]) -> int:
    def desc_len(text: str) -> int:
        return 2 + len(str(text).encode("utf-16-le"))

    total = desc_len(device.get("manufacturer", ""))
    total += desc_len(device.get("product", ""))
    serial = str(device.get("serial", "")).strip()
    has_serial = bool(device.get("has_serial", True))
    if has_serial and serial:
        total += desc_len(serial)
    total += STRING_TERMINATOR_BYTES
    return total


def compute_available_ua_bytes(eeprom_size_bytes: int, device: Mapping[str, Any]) -> int:
    string_bytes = compute_string_descriptor_bytes(device)
    return eeprom_size_bytes - FT4232H_HEADER_BYTES - EEPROM_CRC_BYTES - string_bytes


def validate_user_area_fits(payload: bytes, available_ua_bytes: int) -> None:
    if available_ua_bytes < 0:
        raise ValueError(
            f"Available User Area is negative ({available_ua_bytes}B); EEPROM has no room for Vivado payload."
        )
    if len(payload) > available_ua_bytes:
        raise ValueError(
            f"Vivado User Area payload {len(payload)}B exceeds available UA {available_ua_bytes}B; "
            "shorten device.product / vivado.user_area.product or use a 93C56 (256B) EEPROM."
        )
