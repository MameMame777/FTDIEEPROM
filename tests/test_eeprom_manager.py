from __future__ import annotations

from contextlib import contextmanager

import ftdi_eeprom.eeprom_manager as eeprom_manager_module
from ftdi_eeprom.eeprom_manager import Ft4232HEepromManager


class FakeConfigEeprom:
    def __init__(self):
        self.data = b"\x01\x02\x03\x04"
        self.loaded_text = None
        self.commit_calls = []

    def save_config(self, file_obj):
        file_obj.write("[values]\nproduct = Demo\n")

    def load_config(self, file_obj):
        self.loaded_text = file_obj.read()

    def commit(self, dry_run=False):
        self.commit_calls.append(dry_run)


class FakeWritableEeprom:
    def __init__(self):
        self.mirroring = []
        self.manufacturer = []
        self.product = []
        self.serial = []
        self.properties = []

    def enable_mirroring(self, enabled):
        self.mirroring.append(enabled)

    def set_manufacturer_name(self, value):
        self.manufacturer.append(value)

    def set_product_name(self, value):
        self.product.append(value)

    def set_serial_number(self, value):
        self.serial.append(value)

    def set_property(self, name, value):
        self.properties.append((name, value))


class FakeRefreshAdapter:
    def __init__(self):
        self.calls = []

    def reset(self, usb_reset=True):
        self.calls.append(usb_reset)


class FakeRefreshEeprom:
    def __init__(self):
        self._ftdi = FakeRefreshAdapter()


class FakeWindowsWriteEeprom:
    def __init__(self):
        self.data = b"\x01\x02\x03\x04"
        self._ftdi = FakeRefreshAdapter()

    def save_config(self, file_obj):
        file_obj.write("[values]\nproduct = Demo\n")


class FakeWindowsRestoreConfigEeprom(FakeWindowsWriteEeprom):
    def __init__(self):
        super().__init__()
        self.loaded_text = None
        self.commit_calls = []

    def load_config(self, file_obj):
        self.loaded_text = file_obj.read()

    def commit(self, dry_run=False):
        self.commit_calls.append(dry_run)


def test_backup_writes_ini_using_file_object(tmp_path):
    manager = Ft4232HEepromManager()
    eeprom = FakeConfigEeprom()

    artifacts = manager._create_backup_from_eeprom(eeprom, tmp_path / "backup" / "current")

    assert artifacts.bin_path.read_bytes() == b"\x01\x02\x03\x04"
    assert "product = Demo" in artifacts.ini_path.read_text(encoding="utf-8")


def test_restore_config_reads_ini_using_file_object(tmp_path, monkeypatch):
    manager = Ft4232HEepromManager()
    eeprom = FakeConfigEeprom()
    ini_path = tmp_path / "input.ini"
    ini_path.write_text("[values]\nproduct = Loaded\n", encoding="utf-8")

    @contextmanager
    def fake_open(_url):
        yield eeprom

    monkeypatch.setattr(eeprom_manager_module.sys, "platform", "linux")
    monkeypatch.setattr(manager, "open_eeprom", fake_open)

    manager.restore_config("ftdi://ftdi:4232h/1", ini_path, tmp_path / "backup" / "restore")

    assert "product = Loaded" in eeprom.loaded_text
    assert eeprom.commit_calls == [False]


def test_apply_public_properties_uses_string_setters_for_var_strings():
    manager = Ft4232HEepromManager()
    eeprom = FakeWritableEeprom()

    manager._apply_public_properties(
        eeprom,
        {
            "device": {
                "chip": "FT4232H",
                "vendor_id": 0x0403,
                "product_id": 0x6011,
                "manufacturer": "Xilinx",
                "product": "FT4232H Vivado SPI-B Bridge",
                "serial": "FTABPV9D",
                "power_max": 100,
                "has_serial": True,
                "mirror_eeprom": True,
                "pnp": True,
            },
            "channels": {
                "A": {"driver": "D2XX", "type": "UART", "drive_current_ma": 16},
                "B": {"driver": "D2XX", "type": "UART", "drive_current_ma": 16},
                "C": {"driver": "D2XX", "type": "UART", "drive_current_ma": 16},
                "D": {"driver": "D2XX", "type": "UART", "drive_current_ma": 16},
            },
        },
    )

    assert eeprom.mirroring == [True]
    assert eeprom.manufacturer == ["Xilinx"]
    assert eeprom.product == ["FT4232H Vivado SPI-B Bridge"]
    assert eeprom.serial == ["FTABPV9D"]
    assert ("vendor_id", 0x0403) in eeprom.properties
    assert ("product_id", 0x6011) in eeprom.properties


def test_refresh_device_enumeration_uses_ftdi_reset_on_windows(monkeypatch):
    manager = Ft4232HEepromManager()
    eeprom = FakeRefreshEeprom()

    monkeypatch.setattr(eeprom_manager_module.sys, "platform", "win32")

    manager._refresh_device_enumeration(eeprom)

    assert eeprom._ftdi.calls == [True]


def test_write_uses_d2xx_program_eeprom_on_windows(tmp_path, monkeypatch):
    manager = Ft4232HEepromManager()
    eeprom = FakeWindowsWriteEeprom()
    called = {}

    @contextmanager
    def fake_open(_url):
        yield eeprom

    def fake_program_eeprom(program_eeprom_obj, config, user_area_payload):
        called["eeprom"] = program_eeprom_obj
        called["config"] = config
        called["payload"] = user_area_payload

    monkeypatch.setattr(eeprom_manager_module.sys, "platform", "win32")
    monkeypatch.setattr(manager, "open_eeprom", fake_open)
    monkeypatch.setattr(eeprom_manager_module.d2xx_backend, "program_eeprom", fake_program_eeprom)

    config = {
        "device": {
            "chip": "FT4232H",
            "vendor_id": 0x0403,
            "product_id": 0x6011,
            "manufacturer": "Xilinx",
            "product": "FT4232H Vivado Bridge",
            "serial": "FT4232H0001",
            "power_max": 100,
            "has_serial": True,
            "mirror_eeprom": True,
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
            "firmware_id": 0x584A0004,
            "user_area": {"vendor": "Xilinx", "product": "FT4232H JTAG"},
        },
    }

    manager.write("ftdi://ftdi:4232h/1", config, tmp_path / "backup" / "current")

    assert called["eeprom"] is eeprom
    assert called["config"] is config
    assert called["payload"].startswith(b"\x04\x00JX")
    assert eeprom._ftdi.calls == [True]


def test_restore_uses_d2xx_restore_eeprom_on_windows(tmp_path, monkeypatch):
    manager = Ft4232HEepromManager()
    eeprom = FakeWindowsWriteEeprom()
    called = {}
    image_path = tmp_path / "restore.bin"
    image_path.write_bytes(b"\x00\x01\x02\x03")

    @contextmanager
    def fake_open(_url):
        yield eeprom

    def fake_restore_eeprom(restore_eeprom_obj, decoded_config, image, user_area_offset):
        called["eeprom"] = restore_eeprom_obj
        called["config"] = decoded_config
        called["image"] = image
        called["offset"] = user_area_offset

    monkeypatch.setattr(eeprom_manager_module.sys, "platform", "win32")
    monkeypatch.setattr(manager, "open_eeprom", fake_open)
    monkeypatch.setattr(eeprom_manager_module.eeprom_backend, "decode_raw_image", lambda _eeprom, _image: None)
    monkeypatch.setattr(eeprom_manager_module.eeprom_backend, "get_decoded_config", lambda _eeprom: {"vendor_id": 0x0403})
    monkeypatch.setattr(eeprom_manager_module.eeprom_backend, "get_user_area_offset", lambda _eeprom: 26)
    monkeypatch.setattr(eeprom_manager_module.d2xx_backend, "restore_eeprom", fake_restore_eeprom)

    manager.restore("ftdi://ftdi:4232h/1", image_path, tmp_path / "backup" / "restore")

    assert called["eeprom"] is eeprom
    assert called["config"] == {"vendor_id": 0x0403}
    assert called["image"] == b"\x00\x01\x02\x03"
    assert called["offset"] == 26
    assert eeprom._ftdi.calls == [True]


def test_restore_config_uses_d2xx_program_decoded_eeprom_on_windows(tmp_path, monkeypatch):
    manager = Ft4232HEepromManager()
    eeprom = FakeWindowsRestoreConfigEeprom()
    called = {}
    ini_path = tmp_path / "restore.ini"
    ini_path.write_text("[values]\nproduct = Loaded\n", encoding="utf-8")

    @contextmanager
    def fake_open(_url):
        yield eeprom

    def fake_program_decoded_eeprom(program_eeprom_obj, decoded_config, user_area_payload=None):
        called["eeprom"] = program_eeprom_obj
        called["config"] = decoded_config
        called["payload"] = user_area_payload

    monkeypatch.setattr(eeprom_manager_module.sys, "platform", "win32")
    monkeypatch.setattr(manager, "open_eeprom", fake_open)
    monkeypatch.setattr(eeprom_manager_module.eeprom_backend, "get_decoded_config", lambda _eeprom: {"vendor_id": 0x0403})
    monkeypatch.setattr(eeprom_manager_module.d2xx_backend, "program_decoded_eeprom", fake_program_decoded_eeprom)

    manager.restore_config("ftdi://ftdi:4232h/1", ini_path, tmp_path / "backup" / "restore")

    assert "product = Loaded" in eeprom.loaded_text
    assert called["eeprom"] is eeprom
    assert called["config"] == {"vendor_id": 0x0403}
    assert called["payload"] is None
    assert eeprom.commit_calls == []
    assert eeprom._ftdi.calls == [True]