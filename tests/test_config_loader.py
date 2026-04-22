from __future__ import annotations

import json
from pathlib import Path

import pytest

from ftdi_eeprom.config_loader import (
    ConfigValidationError,
    get_default_config,
    iter_eeprom_properties,
    load_config,
    merge_config,
    validate_config,
)


def test_load_config_reads_valid_json(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(get_default_config()), encoding="utf-8")
    config = load_config(path)
    assert config["device"]["chip"] == "FT4232H"
    assert config["vivado"]["enabled"] is True


def test_default_config_file_matches_builtin_default():
    config_path = Path(__file__).resolve().parents[1] / "configs" / "ft4232h_default.json"

    assert load_config(config_path) == get_default_config()


def test_default_config_matches_split_use_profile():
    config = get_default_config()
    assert config["device"]["product"] == "FT4232H Vivado Bridge"
    assert config["channels"]["A"]["driver"] == "D2XX"
    assert config["channels"]["B"]["driver"] == "D2XX"
    assert config["channels"]["C"]["driver"] == "VCP"
    assert config["channels"]["D"]["driver"] == "VCP"
    assert config["channels"]["A"]["drive_current_ma"] == 4
    assert config["channels"]["B"]["drive_current_ma"] == 4
    assert config["channels"]["C"]["drive_current_ma"] == 4
    assert config["channels"]["D"]["drive_current_ma"] == 4
    assert config["udev"]["unbind_interfaces"] == ["00", "01"]
    assert config["runtime_profile"]["channel_b"]["role"] == "spi"


def test_merge_config_overrides_nested_values():
    merged = merge_config(get_default_config(), {"channels": {"B": {"driver": "D2XX"}}})
    assert merged["channels"]["B"]["driver"] == "D2XX"
    assert merged["channels"]["A"]["driver"] == "D2XX"


def test_iter_eeprom_properties_keeps_user_facing_string_property_names():
    properties = dict(iter_eeprom_properties(get_default_config()))

    assert properties["manufacturer"] == "Xilinx"
    assert properties["product"] == "FT4232H Vivado Bridge"
    assert properties["serial"] == "FT4232H0001"


def test_validate_config_rejects_runtime_mpsse_keys():
    config = get_default_config()
    config["channels"]["B"]["mpsse"] = {"clock_hz": 1000000}
    with pytest.raises(ConfigValidationError):
        validate_config(config)


def test_validate_config_rejects_non_absolute_script_path():
    config = get_default_config()
    config["udev"]["script_path"] = "ftdi-unbind.sh"
    with pytest.raises(ConfigValidationError):
        validate_config(config)


def test_validate_config_rejects_non_xilinx_manufacturer_for_vivado():
    config = get_default_config()
    config["device"]["manufacturer"] = "FTDI"
    with pytest.raises(ConfigValidationError, match="device.manufacturer must be Xilinx"):
        validate_config(config)
