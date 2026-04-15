from __future__ import annotations

import struct

from ftdi_eeprom.vivado_config import VIVADO_FIRMWARE_ID, build_user_area_payload, build_vivado_preset, has_vivado_payload


def test_firmware_id_pack_matches_expected_bytes():
    assert struct.pack("<I", VIVADO_FIRMWARE_ID) == b"\x04\x00JX"


def test_user_area_payload_contains_null_terminated_strings():
    payload = build_user_area_payload(build_vivado_preset())
    assert payload.startswith(struct.pack("<I", VIVADO_FIRMWARE_ID))
    assert payload.endswith(b"\x00")
    assert b"Xilinx\x00" in payload
    assert b"FT4232H JTAG\x00" in payload


def test_vivado_preset_enables_all_d2xx_drivers_and_drive_16ma():
    config = build_vivado_preset()
    assert has_vivado_payload(config) is True
    for channel_name in ("A", "B", "C", "D"):
        assert config["channels"][channel_name]["driver"] == "D2XX"
        assert config["channels"][channel_name]["drive_current_ma"] == 16
