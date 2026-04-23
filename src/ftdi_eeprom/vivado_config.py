from __future__ import annotations

import struct
from typing import Any, Mapping

from .config_loader import get_default_config, merge_config

VIVADO_FIRMWARE_ID = 0x584A0004


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
