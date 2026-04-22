from __future__ import annotations

from types import SimpleNamespace

import pytest

from ftdi_eeprom.eeprom_backend import (
    PrivateApiError,
    decode_raw_image,
    get_decoded_config,
    read_user_area,
    write_raw_image,
    write_user_area,
)


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
        self._config = {"vendor_id": 0x0403}
        self._valid = True
        self.synced = False
        self.crc_updated = False
        self.decoded = False
        self.crc_checked = None

    def _sync_eeprom(self):
        self.synced = True

    def _update_crc(self):
        self.crc_updated = True

    def _compute_crc(self, image, check):
        self.crc_checked = (bytes(image), check)
        self._valid = True

    def _decode_eeprom(self):
        self.decoded = True


def test_read_user_area_reads_requested_bytes():
    eeprom = FakeEeprom()
    assert read_user_area(eeprom, 8, 4) == bytes([8, 9, 10, 11])


def test_read_user_area_supports_pyftdi_properties_dict_shape():
    eeprom = FakeEeprom()
    eeprom._PROPERTIES = {0x0800: SimpleNamespace(user=8)}
    eeprom.device_version = 0x0800

    assert read_user_area(eeprom, 8, 4) == bytes([8, 9, 10, 11])


def test_write_user_area_updates_buffer_and_calls_overwrite():
    eeprom = FakeEeprom()
    payload = b"ABCD"
    write_user_area(eeprom, 8, payload, dry_run=False)
    assert eeprom.synced is True
    assert eeprom.crc_updated is True
    assert eeprom._ftdi.last_image[8:12] == payload


def test_write_user_area_preserves_trailing_bytes():
    eeprom = FakeEeprom()
    original_tail = bytes(eeprom._eeprom[12:-2])

    write_user_area(eeprom, 8, b"ABCD", dry_run=False)

    assert bytes(eeprom._eeprom[12:-2]) == original_tail


def test_write_raw_image_validates_image_length():
    eeprom = FakeEeprom()
    with pytest.raises(PrivateApiError):
        write_raw_image(eeprom, b"short", dry_run=False)


def test_get_decoded_config_returns_copy_of_private_config():
    eeprom = FakeEeprom()

    config = get_decoded_config(eeprom)

    assert config == {"vendor_id": 0x0403}
    assert config is not eeprom._config
    assert eeprom.synced is True


def test_decode_raw_image_updates_buffer_and_decodes():
    eeprom = FakeEeprom()
    image = bytes(reversed(range(32)))

    result = decode_raw_image(eeprom, image)

    assert result == image
    assert bytes(eeprom._eeprom) == image
    assert eeprom.crc_checked == (image, True)
    assert eeprom.decoded is True
