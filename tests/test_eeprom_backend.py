from __future__ import annotations

from types import SimpleNamespace

import pytest

from ftdi_eeprom.eeprom_backend import PrivateApiError, read_user_area, write_raw_image, write_user_area


class FakeFtdi:
    def __init__(self) -> None:
        self.last_image = None
        self.last_dry_run = None

    def overwrite_eeprom(self, image, dry_run=False):
        self.last_image = bytes(image)
        self.last_dry_run = dry_run


class FakeEeprom:
    def __init__(self) -> None:
        self._eeprom = bytearray(range(32))
        self._PROPERTIES = SimpleNamespace(user=8)
        self._ftdi = FakeFtdi()
        self.synced = False
        self.crc_updated = False

    def _sync_eeprom(self):
        self.synced = True

    def _update_crc(self):
        self.crc_updated = True


def test_read_user_area_reads_requested_bytes():
    eeprom = FakeEeprom()
    assert read_user_area(eeprom, 8, 4) == bytes([8, 9, 10, 11])


def test_write_user_area_updates_buffer_and_calls_overwrite():
    eeprom = FakeEeprom()
    payload = b"ABCD"
    write_user_area(eeprom, 8, payload, dry_run=False)
    assert eeprom.synced is True
    assert eeprom.crc_updated is True
    assert eeprom._ftdi.last_image[8:12] == payload


def test_write_raw_image_validates_image_length():
    eeprom = FakeEeprom()
    with pytest.raises(PrivateApiError):
        write_raw_image(eeprom, b"short", dry_run=False)
