from __future__ import annotations

import argparse
from typing import Sequence

import pytest

from ftdi_eeprom.cli import CliValidationError, build_override_tree, build_parser, resolve_url_from_args, validate_command_args
import ftdi_eeprom.eeprom_manager as eeprom_manager_module
from ftdi_eeprom.eeprom_manager import DeviceInfo, EepromManagerError, Ft4232HEepromManager


class FakeManager(Ft4232HEepromManager):
    def __init__(self, devices: list[DeviceInfo], auto_probe_result: str = "ftdi://ftdi:4232h:SERIAL/2"):
        self._devices = devices
        self._auto_probe_result = auto_probe_result

    def list_devices(self, serial: str | None = None) -> list[DeviceInfo]:
        if serial is None:
            return self._devices
        return [device for device in self._devices if device.serial == serial]

    def format_devices(self, devices: list[DeviceInfo]) -> str:
        return "\n".join(device.serial or "<none>" for device in devices)

    def build_url(self, serial: str | None, interface: int) -> str:
        if serial:
            return f"ftdi://ftdi:4232h:{serial}/{interface}"
        return f"ftdi://ftdi:4232h/{interface}"

    def auto_probe_url(self, serial: str | None = None, interfaces: tuple[int, ...] = (1, 2, 3, 4)) -> str:
        del interfaces
        return self._auto_probe_result.replace("SERIAL", serial or "")


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def test_url_and_serial_are_mutually_exclusive_after_parse():
    args = _parse(["write", "--url", "ftdi://ftdi:4232h/1", "--serial", "ABC", "-c", "device.product=Demo"])
    with pytest.raises(CliValidationError):
        validate_command_args(args)


def test_serial_and_interface_can_be_combined():
    args = _parse(["read", "--serial", "ABC", "--interface", "2"])
    validate_command_args(args)


def test_restore_config_requires_apply_and_allow_partial():
    args = _parse(["restore-config", "example.ini"])
    with pytest.raises(CliValidationError):
        validate_command_args(args)


def test_build_override_tree_parses_json_values():
    assert build_override_tree("device.has_serial=true") == {"device": {"has_serial": True}}


def test_multiple_devices_fail_without_serial():
    args = _parse(["read"])
    manager = FakeManager([DeviceInfo("AAA", None, None, None, None), DeviceInfo("BBB", None, None, None, None)])
    with pytest.raises(CliValidationError):
        resolve_url_from_args(args, manager)


def test_single_unlabeled_device_falls_back_when_serial_filter_misses():
    args = _parse(["read", "--serial", "FT4232H0001"])
    manager = FakeManager([DeviceInfo(None, None, "Quad RS232-HS", None, None)], auto_probe_result="ftdi://ftdi:4232h/1")

    assert resolve_url_from_args(args, manager) == "ftdi://ftdi:4232h/1"


def test_auto_probe_falls_back_to_second_interface(monkeypatch: pytest.MonkeyPatch):
    manager = Ft4232HEepromManager()
    attempted: list[str] = []

    def fake_probe(url: str) -> None:
        attempted.append(url)
        if url.endswith("/1"):
            raise RuntimeError("busy")

    monkeypatch.setattr(manager, "probe_url", fake_probe)
    assert manager.auto_probe_url("ABC") == "ftdi://ftdi:4232h:ABC/2"
    assert attempted == ["ftdi://ftdi:4232h:ABC/1", "ftdi://ftdi:4232h:ABC/2"]


def test_list_devices_wraps_missing_pyusb_backend(monkeypatch: pytest.MonkeyPatch):
    manager = Ft4232HEepromManager()

    class FakeUsbCore:
        class NoBackendError(Exception):
            pass

        @staticmethod
        def find(**_kwargs: object) -> object:
            raise FakeUsbCore.NoBackendError("no backend")

    monkeypatch.setattr(manager, "_import_usb_modules", lambda: (FakeUsbCore, object()))
    monkeypatch.setattr(eeprom_manager_module.sys, "platform", "linux")

    with pytest.raises(EepromManagerError, match="Install a libusb backend such as libusb-1.0"):
        manager.list_devices()


def test_list_devices_uses_d2xx_backend_on_windows(monkeypatch: pytest.MonkeyPatch):
    manager = Ft4232HEepromManager()

    def fake_list_devices(vendor_id: int, product_id: int, serial: str | None) -> list[dict[str, str]]:
        return [{"serial": "FT4232H0001", "description": "FT4232H Dev"}]

    monkeypatch.setattr(eeprom_manager_module.sys, "platform", "win32")
    monkeypatch.setattr(
        eeprom_manager_module.d2xx_backend,
        "list_devices",
        fake_list_devices,
    )

    devices = manager.list_devices()

    assert devices == [DeviceInfo("FT4232H0001", None, "FT4232H Dev", None, None)]


def test_open_eeprom_uses_d2xx_backend_on_windows(monkeypatch: pytest.MonkeyPatch):
    manager = Ft4232HEepromManager()
    monkeypatch.setattr(eeprom_manager_module.sys, "platform", "win32")

    class FakeEeprom:
        def close(self) -> None:
            return

    fake_eeprom = FakeEeprom()

    def fake_open_eeprom(url: str, vendor_id: int, product_id: int, chip_name: str) -> FakeEeprom:
        return fake_eeprom

    monkeypatch.setattr(
        eeprom_manager_module.d2xx_backend,
        "open_eeprom",
        fake_open_eeprom,
    )

    with manager.open_eeprom("ftdi://ftdi:4232h:FT4232H0001/1") as eeprom:
        assert eeprom is fake_eeprom


def test_open_eeprom_wraps_missing_pyusb_backend_on_linux(monkeypatch: pytest.MonkeyPatch):
    manager = Ft4232HEepromManager()

    class FakeUsbCore:
        class NoBackendError(Exception):
            pass

        @staticmethod
        def find(**_kwargs: object) -> object:
            raise FakeUsbCore.NoBackendError("no backend")

    monkeypatch.setattr(manager, "_import_usb_modules", lambda: (FakeUsbCore, object()))
    monkeypatch.setattr(eeprom_manager_module.sys, "platform", "linux")
    monkeypatch.setattr(
        manager,
        "_import_pyftdi_eeprom",
        lambda: pytest.fail("pyftdi import should not be reached when PyUSB has no backend"),
    )

    with pytest.raises(EepromManagerError, match="Install a libusb backend such as libusb-1.0"):
        with manager.open_eeprom("ftdi://ftdi:4232h:FT4232H0001/1"):
            pass