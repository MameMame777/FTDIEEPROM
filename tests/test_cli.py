from __future__ import annotations

import argparse

import pytest

from ftdi_eeprom.cli import CliValidationError, build_override_tree, build_parser, resolve_url_from_args, validate_command_args
from ftdi_eeprom.eeprom_manager import DeviceInfo, EepromManagerError, Ft4232HEepromManager


class FakeManager:
    def __init__(self, devices, auto_probe_result="ftdi://ftdi:4232h:SERIAL/2"):
        self._devices = devices
        self._auto_probe_result = auto_probe_result

    def list_devices(self, serial=None):
        if serial is None:
            return self._devices
        return [device for device in self._devices if device.serial == serial]

    def format_devices(self, devices):
        return "\n".join(device.serial or "<none>" for device in devices)

    def build_url(self, serial, interface):
        return f"ftdi://ftdi:4232h:{serial}/{interface}"

    def auto_probe_url(self, serial):
        return self._auto_probe_result.replace("SERIAL", serial or "")


def _parse(argv):
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


def test_auto_probe_falls_back_to_second_interface(monkeypatch):
    manager = Ft4232HEepromManager()
    attempted = []

    def fake_probe(url):
        attempted.append(url)
        if url.endswith("/1"):
            raise RuntimeError("busy")

    monkeypatch.setattr(manager, "probe_url", fake_probe)
    assert manager.auto_probe_url("ABC") == "ftdi://ftdi:4232h:ABC/2"
    assert attempted == ["ftdi://ftdi:4232h:ABC/1", "ftdi://ftdi:4232h:ABC/2"]


def test_list_devices_wraps_missing_pyusb_backend(monkeypatch):
    manager = Ft4232HEepromManager()

    class FakeUsbCore:
        class NoBackendError(Exception):
            pass

        @staticmethod
        def find(**_kwargs):
            raise FakeUsbCore.NoBackendError("no backend")

    monkeypatch.setattr(manager, "_import_usb_modules", lambda: (FakeUsbCore, object()))

    with pytest.raises(EepromManagerError, match="PyUSB backend is not available"):
        manager.list_devices()