from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

CHIP_NAME = "FT4232H"
CHANNEL_NAMES = ("A", "B", "C", "D")
ALLOWED_DRIVERS = {"D2XX", "VCP"}
ALLOWED_TYPES = {"UART", "RS485"}
ALLOWED_DRIVE_CURRENTS = {4, 8, 12, 16}
ALLOWED_UNBIND_INTERFACES = {"00", "01", "02", "03"}
RUNTIME_ONLY_KEYS = {
    "mpsse",
    "mpsse_gpio",
    "gpio_direction",
    "gpio_initial_state",
    "gpio_initial_value",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "device": {
        "chip": CHIP_NAME,
        "vendor_id": 0x0403,
        "product_id": 0x6011,
        "manufacturer": "Xilinx",
        "product": "FT4232H Vivado Bridge",
        "serial": "FT4232H0001",
        "power_max": 100,
        "has_serial": True,
        "pnp": True,
    },
    "channels": {
        "A": {"driver": "D2XX", "type": "UART", "drive_current_ma": 4},
        "B": {"driver": "D2XX", "type": "UART", "drive_current_ma": 4},
        "C": {"driver": "VCP", "type": "UART", "drive_current_ma": 4},
        "D": {"driver": "VCP", "type": "UART", "drive_current_ma": 4},
    },
    "vivado": {
        "enabled": True,
        "firmware_id": 0x584A0004,
        "user_area": {
            "vendor": "Xilinx",
            "product": "FT4232H JTAG",
        },
    },
    "runtime_profile": {
        "channel_a": {"role": "vivado_jtag", "host": "windows"},
        "channel_b": {"role": "spi", "host": "linux", "interface": 2},
    },
    "udev": {
        "group": "FPGAuser",
        "mode": "0660",
        "script_path": "/usr/local/bin/ftdi-unbind.sh",
        "unbind_interfaces": ["00", "01"],
    },
}


class ConfigValidationError(ValueError):
    """Raised when a JSON configuration is invalid."""


def get_default_config() -> dict[str, Any]:
    return deepcopy(DEFAULT_CONFIG)


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigValidationError(f"Configuration file not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigValidationError(
            f"Invalid JSON in {config_path}: line {exc.lineno}, column {exc.colno}"
        ) from exc
    validate_config(config)
    return config


def validate_config(config: Mapping[str, Any]) -> None:
    if not isinstance(config, Mapping):
        raise ConfigValidationError("Configuration must be a JSON object")

    for key in ("device", "channels"):
        if key not in config:
            raise ConfigValidationError(f"Missing top-level key: {key}")

    _validate_device(config["device"])
    _validate_channels(config["channels"])

    if "vivado" in config:
        _validate_vivado(config["vivado"], config["device"])
    if "udev" in config:
        _validate_udev(config["udev"])
    if "runtime_profile" in config and not isinstance(config["runtime_profile"], Mapping):
        raise ConfigValidationError("runtime_profile must be an object when provided")


def merge_config(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = merge_config(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def iter_eeprom_properties(config: Mapping[str, Any]) -> list[tuple[str, Any]]:
    validate_config(config)
    device = config["device"]
    channels = config["channels"]
    properties: list[tuple[str, Any]] = [
        ("vendor_id", device["vendor_id"]),
        ("product_id", device["product_id"]),
        ("manufacturer", device["manufacturer"]),
        ("product", device["product"]),
        ("power_max", device["power_max"]),
        ("has_serial", bool(device.get("has_serial", True))),
    ]
    serial_value = str(device.get("serial", "")).strip()
    if serial_value:
        properties.append(("serial", serial_value))

    for index, channel_name in enumerate(CHANNEL_NAMES):
        channel = channels[channel_name]
        prefix = channel_name.lower()
        properties.append((f"channel_{prefix}_driver", channel["driver"]))
        properties.append((f"channel_{prefix}_type", channel["type"]))
        properties.append((f"group_{index}_drive", channel["drive_current_ma"]))
    return properties


def _validate_device(device: Any) -> None:
    if not isinstance(device, Mapping):
        raise ConfigValidationError("device must be an object")
    for key in ("chip", "vendor_id", "product_id", "manufacturer", "product", "power_max"):
        if key not in device:
            raise ConfigValidationError(f"device.{key} is required")
    if device["chip"] != CHIP_NAME:
        raise ConfigValidationError(f"device.chip must be {CHIP_NAME}")
    _validate_int(device["vendor_id"], "device.vendor_id", minimum=0, maximum=0xFFFF)
    _validate_int(device["product_id"], "device.product_id", minimum=0, maximum=0xFFFF)
    _validate_int(device["power_max"], "device.power_max", minimum=0, maximum=500)
    for key in ("manufacturer", "product"):
        if not str(device[key]).strip():
            raise ConfigValidationError(f"device.{key} must be a non-empty string")
    if "serial" in device and not isinstance(device["serial"], str):
        raise ConfigValidationError("device.serial must be a string when provided")
    if "has_serial" in device and not isinstance(device["has_serial"], bool):
        raise ConfigValidationError("device.has_serial must be a boolean")
    if "pnp" in device and not isinstance(device["pnp"], bool):
        raise ConfigValidationError("device.pnp must be a boolean")


def _validate_channels(channels: Any) -> None:
    if not isinstance(channels, Mapping):
        raise ConfigValidationError("channels must be an object")
    for channel_name in CHANNEL_NAMES:
        if channel_name not in channels:
            raise ConfigValidationError(f"channels.{channel_name} is required")
        channel = channels[channel_name]
        if not isinstance(channel, Mapping):
            raise ConfigValidationError(f"channels.{channel_name} must be an object")
        for key in ("driver", "type", "drive_current_ma"):
            if key not in channel:
                raise ConfigValidationError(f"channels.{channel_name}.{key} is required")
        if channel["driver"] not in ALLOWED_DRIVERS:
            raise ConfigValidationError(
                f"channels.{channel_name}.driver must be one of {sorted(ALLOWED_DRIVERS)}"
            )
        if channel["type"] not in ALLOWED_TYPES:
            raise ConfigValidationError(
                f"channels.{channel_name}.type must be one of {sorted(ALLOWED_TYPES)}"
            )
        if channel["drive_current_ma"] not in ALLOWED_DRIVE_CURRENTS:
            raise ConfigValidationError(
                f"channels.{channel_name}.drive_current_ma must be one of {sorted(ALLOWED_DRIVE_CURRENTS)}"
            )
        if any(key in RUNTIME_ONLY_KEYS or key.startswith("mpsse") for key in channel):
            raise ConfigValidationError(
                f"channels.{channel_name} contains runtime-only MPSSE keys; move them to runtime_profile"
            )


def _validate_vivado(vivado: Any, device: Mapping[str, Any]) -> None:
    if not isinstance(vivado, Mapping):
        raise ConfigValidationError("vivado must be an object")
    enabled = vivado.get("enabled", False)
    if "enabled" in vivado and not isinstance(enabled, bool):
        raise ConfigValidationError("vivado.enabled must be a boolean")
    if enabled and str(device.get("manufacturer", "")).strip() != "Xilinx":
        raise ConfigValidationError("device.manufacturer must be Xilinx when vivado.enabled is true")
    firmware_id = vivado.get("firmware_id", 0x584A0004)
    _validate_int(firmware_id, "vivado.firmware_id", minimum=0, maximum=0xFFFFFFFF)
    user_area = vivado.get("user_area", {})
    if not isinstance(user_area, Mapping):
        raise ConfigValidationError("vivado.user_area must be an object")
    vendor = user_area.get("vendor", device.get("manufacturer", ""))
    product = user_area.get("product", device.get("product", ""))
    if not str(vendor).strip() or not str(product).strip():
        raise ConfigValidationError("vivado.user_area vendor/product strings must be non-empty")


def _validate_udev(udev: Any) -> None:
    if not isinstance(udev, Mapping):
        raise ConfigValidationError("udev must be an object")
    for key in ("group", "mode", "script_path", "unbind_interfaces"):
        if key not in udev:
            raise ConfigValidationError(f"udev.{key} is required")
    if not str(udev["group"]).strip():
        raise ConfigValidationError("udev.group must be a non-empty string")
    mode = str(udev["mode"])
    if len(mode) != 4 or any(ch not in "01234567" for ch in mode):
        raise ConfigValidationError("udev.mode must be a four-digit octal string, for example 0660")
    script_path_text = str(udev["script_path"])
    script_path = Path(script_path_text)
    posix_script_path = PurePosixPath(script_path_text)
    if not script_path.is_absolute() and not posix_script_path.is_absolute():
        raise ConfigValidationError("udev.script_path must be an absolute file path")
    interfaces = udev["unbind_interfaces"]
    if not isinstance(interfaces, list) or not interfaces:
        raise ConfigValidationError("udev.unbind_interfaces must be a non-empty list")
    invalid = [value for value in interfaces if value not in ALLOWED_UNBIND_INTERFACES]
    if invalid:
        raise ConfigValidationError(
            f"udev.unbind_interfaces contains invalid values: {invalid}; allowed values are {sorted(ALLOWED_UNBIND_INTERFACES)}"
        )


def _validate_int(value: Any, field_name: str, minimum: int, maximum: int) -> None:
    if not isinstance(value, int):
        raise ConfigValidationError(f"{field_name} must be an integer")
    if value < minimum or value > maximum:
        raise ConfigValidationError(f"{field_name} must be between {minimum} and {maximum}")
