from __future__ import annotations

import json
from pathlib import Path
import struct

import pytest

from ftdi_eeprom.vivado_config import (
    VIVADO_FIRMWARE_ID,
    build_user_area_payload,
    build_vivado_preset,
    compute_available_ua_bytes,
    compute_string_descriptor_bytes,
    has_vivado_payload,
    validate_user_area_fits,
)


def test_firmware_id_pack_matches_expected_bytes():
    assert struct.pack("<I", VIVADO_FIRMWARE_ID) == b"\x04\x00JX"


def test_user_area_payload_contains_null_terminated_strings():
    payload = build_user_area_payload(build_vivado_preset())
    assert payload.startswith(struct.pack("<I", VIVADO_FIRMWARE_ID))
    assert payload.endswith(b"\x00")
    assert b"Xilinx\x00" in payload
    assert b"FT4232H JTAG\x00" in payload


def test_vivado_config_file_matches_builtin_preset():
    config_path = Path(__file__).resolve().parents[1] / "configs" / "ft4232h_vivado.json"

    assert json.loads(config_path.read_text(encoding="utf-8")) == build_vivado_preset()


def test_vivado_preset_matches_xilinx_program_ftdi_ft4232h_defaults():
    config = build_vivado_preset()
    assert has_vivado_payload(config) is True
    assert config["device"]["manufacturer"] == "Xilinx"
    assert config["channels"]["A"]["driver"] == "D2XX"
    assert config["channels"]["B"]["driver"] == "VCP"
    assert config["channels"]["C"]["driver"] == "VCP"
    assert config["channels"]["D"]["driver"] == "VCP"
    for channel_name in ("A", "B", "C", "D"):
        assert config["channels"][channel_name]["drive_current_ma"] == 4


def test_validate_user_area_fits_accepts_payload_within_budget():
    payload = build_user_area_payload(build_vivado_preset())
    validate_user_area_fits(payload, available_ua_bytes=len(payload))
    validate_user_area_fits(payload, available_ua_bytes=len(payload) + 32)


def test_validate_user_area_fits_rejects_oversized_payload():
    payload = build_user_area_payload(build_vivado_preset())
    with pytest.raises(ValueError, match="exceeds available UA"):
        validate_user_area_fits(payload, available_ua_bytes=len(payload) - 1)


def test_validate_user_area_fits_rejects_negative_room():
    with pytest.raises(ValueError, match="negative"):
        validate_user_area_fits(b"\x00\x01", available_ua_bytes=-1)


def test_compute_string_descriptor_bytes_counts_utf16_and_headers():
    device = {"manufacturer": "Xilinx", "product": "FT4232H", "serial": "FT4232H0001", "has_serial": True}
    # Xilinx: 2 + 12, FT4232H: 2 + 14, FT4232H0001: 2 + 22, terminator: 2
    assert compute_string_descriptor_bytes(device) == 14 + 16 + 24 + 2


def test_compute_string_descriptor_bytes_skips_serial_when_disabled():
    device = {"manufacturer": "Xilinx", "product": "FT4232H", "serial": "X", "has_serial": False}
    assert compute_string_descriptor_bytes(device) == 14 + 16 + 2


def test_compute_available_ua_bytes_for_93c46_with_default_preset():
    device = build_vivado_preset()["device"]
    device["product"] = "FT4232H"
    device["serial"] = "FT4232H0001"
    # 128 - header(26) - crc(2) - strings(56) = 44
    assert compute_available_ua_bytes(128, device) == 44


def test_compute_available_ua_bytes_for_93c56_with_default_preset():
    device = build_vivado_preset()["device"]
    assert compute_available_ua_bytes(256, device) > 100
