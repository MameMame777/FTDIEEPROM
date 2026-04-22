from __future__ import annotations

from types import SimpleNamespace

import pytest

from ftdi_eeprom import d2xx_backend


class FakeFtd2xxModule:
    def __init__(self, details):
        self._details = details

    def createDeviceInfoList(self):
        return len(self._details)

    def getDeviceInfoDetail(self, index, update=False):
        return self._details[index]


def test_list_devices_groups_interfaces_by_base_serial(monkeypatch):
    vendor_id = 0x0403
    product_id = 0x6011
    details = [
        {
            "id": (vendor_id << 16) | product_id,
            "serial": b"FT4232H0001A",
            "description": b"FT4232H Device A",
        },
        {
            "id": (vendor_id << 16) | product_id,
            "serial": b"FT4232H0001B",
            "description": b"FT4232H Device B",
        },
        {
            "id": (vendor_id << 16) | product_id,
            "serial": b"FT4232H0001C",
            "description": b"FT4232H Device C",
        },
        {
            "id": (vendor_id << 16) | product_id,
            "serial": b"FT4232H0001D",
            "description": b"FT4232H Device D",
        },
    ]
    monkeypatch.setattr(d2xx_backend, "_import_ftd2xx", lambda: FakeFtd2xxModule(details))

    devices = d2xx_backend.list_devices(vendor_id, product_id)

    assert devices == [{"serial": "FT4232H0001", "description": "FT4232H Device"}]


def test_list_devices_handles_single_letter_d2xx_serials(monkeypatch):
    vendor_id = 0x0403
    product_id = 0x6011
    details = [
        {
            "id": (vendor_id << 16) | product_id,
            "serial": b"A",
            "description": b"Quad RS232-HS A",
        },
        {
            "id": (vendor_id << 16) | product_id,
            "serial": b"B",
            "description": b"Quad RS232-HS B",
        },
        {
            "id": (vendor_id << 16) | product_id,
            "serial": b"C",
            "description": b"Quad RS232-HS C",
        },
        {
            "id": (vendor_id << 16) | product_id,
            "serial": b"D",
            "description": b"Quad RS232-HS D",
        },
    ]
    monkeypatch.setattr(d2xx_backend, "_import_ftd2xx", lambda: FakeFtd2xxModule(details))

    devices = d2xx_backend.list_devices(vendor_id, product_id)

    assert devices == [{"serial": None, "description": "Quad RS232-HS"}]


def test_parse_ftdi_url_accepts_standard_scheme():
    assert d2xx_backend._parse_url("ftdi://ftdi:4232h:FT4232H0001/2", "4232h") == ("FT4232H0001", 2)


def test_parse_ftdi_url_rejects_unknown_scheme():
    with pytest.raises(RuntimeError):
        d2xx_backend._parse_url("unsupported://FT4232H0001", "4232h")


def test_d2xx_adapter_reset_prefers_cycle_port():
    class FakeHandle:
        def __init__(self):
            self.calls = []

        def cyclePort(self):
            self.calls.append("cyclePort")

    handle = FakeHandle()
    adapter = object.__new__(d2xx_backend._D2xxFtdiAdapter)
    adapter._handle = handle
    adapter._connected = True

    adapter.reset()

    assert handle.calls == ["cyclePort"]


def test_d2xx_adapter_close_ignores_handle_close_errors():
    class FakeHandle:
        def close(self):
            raise RuntimeError("device already disconnected")

    adapter = object.__new__(d2xx_backend._D2xxFtdiAdapter)
    adapter._handle = FakeHandle()
    adapter._connected = True

    adapter.close()

    assert adapter._connected is False


def test_program_eeprom_maps_config_to_ftd2xx_progdata_fields():
    class FakeHandle:
        def __init__(self):
            self.progdata = SimpleNamespace(
                ManufacturerId=b"FT",
                PnP=0,
                SerNumEnable8=0,
                ADriveCurrent=0,
                BDriveCurrent=0,
                CDriveCurrent=0,
                DDriveCurrent=0,
                AIsVCP8=1,
                BIsVCP8=1,
                CIsVCP8=1,
                DIsVCP8=1,
            )
            self.programmed = None
            self.user_area = None

        def eeRead(self):
            return self.progdata

        def eeProgram(self, progdata):
            self.programmed = progdata

        def eeUAWrite(self, data):
            self.user_area = data

    eeprom = SimpleNamespace(_ftdi=SimpleNamespace(_handle=FakeHandle()))
    config = {
        "device": {
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
            "A": {"driver": "D2XX", "drive_current_ma": 4},
            "B": {"driver": "VCP", "drive_current_ma": 4},
            "C": {"driver": "VCP", "drive_current_ma": 4},
            "D": {"driver": "VCP", "drive_current_ma": 4},
        },
    }

    d2xx_backend.program_eeprom(eeprom, config, b"payload")

    handle = eeprom._ftdi._handle
    assert handle.programmed is handle.progdata
    assert handle.progdata.VendorId == 0x0403
    assert handle.progdata.ProductId == 0x6011
    assert handle.progdata.Manufacturer == b"Xilinx"
    assert handle.progdata.ManufacturerId == b"FT"
    assert handle.progdata.Description == b"FT4232H Vivado Bridge"
    assert handle.progdata.SerialNumber == b"FT4232H0001"
    assert handle.progdata.MaxPower == 100
    assert handle.progdata.PnP == 1
    assert handle.progdata.SerNumEnable8 == 1
    assert handle.progdata.ADriveCurrent == 4
    assert handle.progdata.BDriveCurrent == 4
    assert handle.progdata.CDriveCurrent == 4
    assert handle.progdata.DDriveCurrent == 4
    assert handle.progdata.AIsVCP8 == 0
    assert handle.progdata.BIsVCP8 == 1
    assert handle.progdata.CIsVCP8 == 1
    assert handle.progdata.DIsVCP8 == 1
    assert handle.user_area == b"payload"


def test_restore_eeprom_uses_decoded_config_and_device_user_area_size():
    class FakeHandle:
        def __init__(self):
            self.progdata = SimpleNamespace(
                ManufacturerId=b"FT",
                PnP=0,
                SerNumEnable8=0,
                SelfPowered=0,
                RemoteWakeup=0,
                PullDownEnable8=0,
                ADriveCurrent=0,
                ASlowSlew=0,
                ASchmittInput=0,
                ARIIsTXDEN=0,
                BDriveCurrent=0,
                BSlowSlew=0,
                BSchmittInput=0,
                BRIIsTXDEN=0,
                CDriveCurrent=0,
                DDriveCurrent=0,
                AIsVCP8=1,
                BIsVCP8=1,
                CIsVCP8=1,
                DIsVCP8=1,
            )
            self.programmed = None
            self.user_area = None

        def eeRead(self):
            return self.progdata

        def eeProgram(self, progdata):
            self.programmed = progdata

        def eeUASize(self):
            return 4

        def eeUAWrite(self, data):
            self.user_area = data

    eeprom = SimpleNamespace(_ftdi=SimpleNamespace(_handle=FakeHandle()))
    decoded_config = {
        "vendor_id": 0x0403,
        "product_id": 0x6011,
        "manufacturer": "Xilinx",
        "product": "FT4232H Vivado Bridge",
        "serial": "FT4232H0001",
        "power_max": 100,
        "has_serial": True,
        "pnp": True,
        "self_powered": True,
        "remote_wakeup": True,
        "suspend_pull_down": True,
        "channel_a_driver": "D2XX",
        "channel_a_type": "UART",
        "group_0_drive": 4,
        "group_0_slow_slew": True,
        "group_0_schmitt": True,
        "channel_b_driver": "VCP",
        "channel_b_type": "RS485",
        "group_1_drive": 8,
        "group_1_slow_slew": False,
        "group_1_schmitt": True,
        "channel_c_driver": "VCP",
        "channel_c_type": "UART",
        "group_2_drive": 4,
        "channel_d_driver": "VCP",
        "channel_d_type": "UART",
        "group_3_drive": 4,
    }
    image = bytes(range(32))

    d2xx_backend.restore_eeprom(eeprom, decoded_config, image, 8)

    handle = eeprom._ftdi._handle
    assert handle.programmed is handle.progdata
    assert handle.progdata.SelfPowered == 1
    assert handle.progdata.RemoteWakeup == 1
    assert handle.progdata.PullDownEnable8 == 1
    assert handle.progdata.ASlowSlew == 1
    assert handle.progdata.ASchmittInput == 1
    assert handle.progdata.BIsVCP8 == 1
    assert handle.progdata.BRIIsTXDEN == 1
    assert handle.user_area == image[8:12]