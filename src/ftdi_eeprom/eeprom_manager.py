from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator, Mapping

from . import eeprom_backend
from .config_loader import iter_eeprom_properties
from .vivado_config import build_user_area_payload, has_vivado_payload


class EepromManagerError(RuntimeError):
    """Raised when the EEPROM manager cannot complete an operation."""


class DeviceSelectionError(EepromManagerError):
    """Raised when a target device cannot be selected safely."""


@dataclass(frozen=True)
class DeviceInfo:
    serial: str | None
    manufacturer: str | None
    product: str | None
    bus: int | None
    address: int | None


@dataclass(frozen=True)
class BackupArtifacts:
    bin_path: Path
    ini_path: Path


@dataclass(frozen=True)
class WriteResult:
    url: str
    backup: BackupArtifacts
    property_names: list[str]
    user_area_length: int


class Ft4232HEepromManager:
    def __init__(self, vendor_id: int = 0x0403, product_id: int = 0x6011, chip_name: str = "4232h") -> None:
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.chip_name = chip_name

    def list_devices(self, serial: str | None = None) -> list[DeviceInfo]:
        usb_core, usb_util = self._import_usb_modules()
        devices = usb_core.find(find_all=True, idVendor=self.vendor_id, idProduct=self.product_id) or []
        matches: list[DeviceInfo] = []
        for device in devices:
            serial_text = self._safe_usb_string(usb_util, device, getattr(device, "iSerialNumber", 0))
            if serial and serial_text != serial:
                continue
            matches.append(
                DeviceInfo(
                    serial=serial_text,
                    manufacturer=self._safe_usb_string(usb_util, device, getattr(device, "iManufacturer", 0)),
                    product=self._safe_usb_string(usb_util, device, getattr(device, "iProduct", 0)),
                    bus=getattr(device, "bus", None),
                    address=getattr(device, "address", None),
                )
            )
        return matches

    def format_devices(self, devices: list[DeviceInfo]) -> str:
        lines = []
        for index, device in enumerate(devices, start=1):
            serial = device.serial or "<no-serial>"
            product = device.product or "<unknown-product>"
            location = ""
            if device.bus is not None and device.address is not None:
                location = f" bus={device.bus} address={device.address}"
            lines.append(f"{index}. serial={serial} product={product}{location}")
        return "\n".join(lines)

    def build_url(self, serial: str | None, interface: int) -> str:
        if serial:
            return f"ftdi://ftdi:{self.chip_name}:{serial}/{interface}"
        return f"ftdi://ftdi:{self.chip_name}/{interface}"

    def auto_probe_url(self, serial: str | None = None, interfaces: tuple[int, ...] = (1, 2, 3, 4)) -> str:
        errors: list[str] = []
        for interface in interfaces:
            url = self.build_url(serial, interface)
            try:
                self.probe_url(url)
                return url
            except Exception as exc:  # pragma: no cover - exercised with mocks in tests
                errors.append(f"{url}: {exc}")
        error_text = "\n".join(errors)
        raise DeviceSelectionError(f"No accessible FT4232H interface found.\n{error_text}")

    def probe_url(self, url: str) -> None:
        with self.open_eeprom(url):
            return

    @contextmanager
    def open_eeprom(self, url: str) -> Iterator[Any]:
        FtdiEeprom = self._import_pyftdi_eeprom()
        eeprom = FtdiEeprom()
        try:
            eeprom.open(url)
            yield eeprom
        except Exception as exc:  # pragma: no cover - hardware dependent
            raise EepromManagerError(f"Failed to open EEPROM at {url}: {exc}") from exc
        finally:
            close = getattr(eeprom, "close", None)
            if callable(close):
                close()

    def read(self, url: str) -> dict[str, Any]:
        with self.open_eeprom(url) as eeprom:
            raw = bytes(eeprom.data)
            config_text = self._capture_config_text(eeprom)
        return {"url": url, "raw": raw, "config_text": config_text}

    def dump(self, url: str) -> str:
        snapshot = self.read(url)
        raw = snapshot["raw"]
        lines = [
            f"URL: {snapshot['url']}",
            f"EEPROM size: {len(raw)} bytes",
            "",
            "Hex preview:",
            self._format_hexdump(raw[:128]),
        ]
        config_text = snapshot["config_text"].strip()
        if config_text:
            lines.extend(["", "Decoded configuration:", config_text])
        return "\n".join(lines)

    def hexdump(self, url: str) -> str:
        snapshot = self.read(url)
        return self._format_hexdump(snapshot["raw"])

    def backup(self, url: str, basename: str | Path) -> BackupArtifacts:
        with self.open_eeprom(url) as eeprom:
            return self._create_backup_from_eeprom(eeprom, basename)

    def write(self, url: str, config: Mapping[str, Any], backup_prefix: str | Path) -> WriteResult:
        with self.open_eeprom(url) as eeprom:
            backup = self._create_backup_from_eeprom(eeprom, backup_prefix)
            self._apply_public_properties(eeprom, config)
            user_area_payload = build_user_area_payload(config) if has_vivado_payload(config) else b""
            if user_area_payload:
                offset = eeprom_backend.get_user_area_offset(eeprom)
                eeprom_backend.write_user_area(eeprom, offset, user_area_payload, dry_run=False)
            else:
                eeprom.commit(dry_run=False)
        property_names = [name for name, _ in iter_eeprom_properties(config)]
        return WriteResult(url=url, backup=backup, property_names=property_names, user_area_length=len(user_area_payload))

    def restore(self, url: str, image_path: str | Path, backup_prefix: str | Path) -> BackupArtifacts:
        image = Path(image_path).read_bytes()
        with self.open_eeprom(url) as eeprom:
            backup = self._create_backup_from_eeprom(eeprom, backup_prefix)
            eeprom_backend.write_raw_image(eeprom, image, dry_run=False)
        return backup

    def restore_config(self, url: str, ini_path: str | Path, backup_prefix: str | Path) -> BackupArtifacts:
        with self.open_eeprom(url) as eeprom:
            backup = self._create_backup_from_eeprom(eeprom, backup_prefix)
            eeprom.load_config(str(ini_path))
            eeprom.commit(dry_run=False)
        return backup

    def default_backup_prefix(self, operation: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return Path.cwd() / f"ftdi-eeprom-{operation}-backup-{timestamp}"

    def _apply_public_properties(self, eeprom: Any, config: Mapping[str, Any]) -> None:
        if config["device"].get("mirror_eeprom", True):
            eeprom.enable_mirroring(True)
        for property_name, property_value in iter_eeprom_properties(config):
            eeprom.set_property(property_name, property_value)

    def _create_backup_from_eeprom(self, eeprom: Any, basename: str | Path) -> BackupArtifacts:
        base = Path(basename)
        if base.suffix:
            base = base.with_suffix("")
        base.parent.mkdir(parents=True, exist_ok=True)
        bin_path = base.with_suffix(".bin")
        ini_path = base.with_suffix(".ini")
        bin_path.write_bytes(bytes(eeprom.data))
        eeprom.save_config(str(ini_path))
        return BackupArtifacts(bin_path=bin_path, ini_path=ini_path)

    def _capture_config_text(self, eeprom: Any) -> str:
        with TemporaryDirectory() as temp_dir:
            ini_path = Path(temp_dir) / "snapshot.ini"
            eeprom.save_config(str(ini_path))
            return ini_path.read_text(encoding="utf-8")

    def _format_hexdump(self, payload: bytes, width: int = 16) -> str:
        lines = []
        for offset in range(0, len(payload), width):
            chunk = payload[offset : offset + width]
            hex_part = " ".join(f"{byte:02x}" for byte in chunk)
            ascii_part = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
            lines.append(f"{offset:04x}  {hex_part:<{width * 3}}  {ascii_part}")
        return "\n".join(lines) if lines else "<empty>"

    def _import_pyftdi_eeprom(self) -> Any:
        try:
            return import_module("pyftdi.eeprom").FtdiEeprom
        except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
            raise EepromManagerError("pyftdi is required but not installed") from exc

    def _import_usb_modules(self) -> tuple[Any, Any]:
        try:
            return import_module("usb.core"), import_module("usb.util")
        except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
            raise EepromManagerError("pyusb is required but not installed") from exc

    def _safe_usb_string(self, usb_util: Any, device: Any, index: int) -> str | None:
        if not index:
            return None
        try:
            return usb_util.get_string(device, index)
        except Exception:  # pragma: no cover - hardware dependent
            return None
