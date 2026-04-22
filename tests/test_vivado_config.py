from __future__ import annotations

import json
from pathlib import Path
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
