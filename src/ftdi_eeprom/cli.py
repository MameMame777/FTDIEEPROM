from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .config_loader import (
    ConfigValidationError,
    get_default_config,
    load_config,
    merge_config,
    iter_eeprom_properties,
    validate_config,
)
from .eeprom_manager import DeviceSelectionError, EepromManagerError, Ft4232HEepromManager
from .udev_generator import render_install_hint, write_udev_bundle
from .vivado_config import build_user_area_payload, has_vivado_payload


class CliValidationError(ValueError):
    """Raised when CLI arguments are inconsistent."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ftdi_eeprom",
        description="FT4232H EEPROM management CLI with Vivado preset and Linux udev support",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--url", help="Full pyftdi URL, for example ftdi://ftdi:4232h/1")
    common.add_argument("--serial", help="Target FT4232H serial string")
    common.add_argument("--interface", type=int, choices=(1, 2, 3, 4), help="FT4232H interface number")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("read", parents=[common], help="Read and display EEPROM contents")
    subparsers.add_parser("hexdump", parents=[common], help="Show raw EEPROM contents as hex")

    backup_parser = subparsers.add_parser("backup", parents=[common], help="Save EEPROM backup as .bin and .ini")
    backup_parser.add_argument("-o", "--output", required=True, help="Output basename without extension")

    write_parser = subparsers.add_parser("write", parents=[common], help="Write EEPROM settings from JSON or key=value overrides")
    write_parser.add_argument("--config", help="Path to a JSON configuration file")
    write_parser.add_argument(
        "-c",
        "--set",
        action="append",
        dest="set_values",
        default=[],
        metavar="KEY=VALUE",
        help="Override a config key using dotted paths, for example channels.B.driver=D2XX",
    )
    write_parser.add_argument("--apply", action="store_true", help="Write changes to EEPROM")
    write_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    restore_parser = subparsers.add_parser("restore", parents=[common], help="Restore a raw .bin EEPROM image")
    restore_parser.add_argument("image", help="Path to a raw .bin EEPROM image")
    restore_parser.add_argument("--apply", action="store_true", help="Write changes to EEPROM")
    restore_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    restore_config_parser = subparsers.add_parser(
        "restore-config",
        parents=[common],
        help="Restore config values from a pyftdi INI file",
    )
    restore_config_parser.add_argument("ini_file", help="Path to a pyftdi .ini configuration file")
    restore_config_parser.add_argument("--allow-partial", action="store_true", help="Acknowledge that User Area data is not restored")
    restore_config_parser.add_argument("--apply", action="store_true", help="Write changes to EEPROM")
    restore_config_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    udev_parser = subparsers.add_parser("udev", help="Generate Linux udev rules and install helper")
    udev_parser.add_argument("--config", required=True, help="Path to a JSON configuration file")
    udev_parser.add_argument("-o", "--output", required=True, help="Output directory")

    return parser


def validate_selection_args(args: argparse.Namespace) -> None:
    if getattr(args, "url", None) and (getattr(args, "serial", None) or getattr(args, "interface", None)):
        raise CliValidationError("--url cannot be combined with --serial or --interface")


def validate_command_args(args: argparse.Namespace) -> None:
    if args.command in {"read", "hexdump", "backup", "write", "restore", "restore-config"}:
        validate_selection_args(args)

    if args.command == "write" and not args.config and not args.set_values:
        raise CliValidationError("write requires --config, -c/--set, or both")
    if args.command == "restore" and not args.apply:
        raise CliValidationError("restore requires --apply")
    if args.command == "restore-config":
        if not args.allow_partial:
            raise CliValidationError("restore-config requires --allow-partial")
        if not args.apply:
            raise CliValidationError("restore-config requires --apply")


def resolve_url_from_args(args: argparse.Namespace, manager: Ft4232HEepromManager) -> str:
    if getattr(args, "url", None):
        return args.url

    devices = manager.list_devices(serial=getattr(args, "serial", None))
    if not devices:
        raise CliValidationError("No FT4232H devices found")
    if not getattr(args, "serial", None) and len(devices) > 1:
        raise CliValidationError(
            "Multiple FT4232H devices found. Re-run with --serial or --url:\n" + manager.format_devices(devices)
        )
    if len(devices) > 1:
        raise CliValidationError(
            "Multiple FT4232H devices matched the provided filter. Re-run with --url:\n" + manager.format_devices(devices)
        )

    device = devices[0]
    if getattr(args, "interface", None):
        return manager.build_url(device.serial, args.interface)
    return manager.auto_probe_url(device.serial)


def load_write_config(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(args.config) if args.config else get_default_config()
    for override in args.set_values:
        config = merge_config(config, build_override_tree(override))
    validate_config(config)
    return config


def build_override_tree(entry: str) -> dict[str, Any]:
    if "=" not in entry:
        raise CliValidationError(f"Invalid override '{entry}'. Expected KEY=VALUE")
    dotted_key, raw_value = entry.split("=", 1)
    key_parts = [part for part in dotted_key.split(".") if part]
    if not key_parts:
        raise CliValidationError(f"Invalid override key in '{entry}'")

    value = _parse_override_value(raw_value)
    tree: dict[str, Any] = value
    for key in reversed(key_parts):
        tree = {key: tree}
    return tree


def preview_write_plan(config: dict[str, Any]) -> str:
    lines = [
        "Dry-run only. No EEPROM changes will be written.",
        "",
        "Public EEPROM properties:",
    ]
    for property_name, property_value in iter_eeprom_properties(config):
        lines.append(f"  {property_name} = {property_value}")
    if has_vivado_payload(config):
        payload = build_user_area_payload(config)
        lines.extend(["", f"User Area payload bytes: {len(payload)}"])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        validate_command_args(args)
        manager = Ft4232HEepromManager()

        if args.command == "read":
            print(manager.dump(resolve_url_from_args(args, manager)))
            return 0

        if args.command == "hexdump":
            print(manager.hexdump(resolve_url_from_args(args, manager)))
            return 0

        if args.command == "backup":
            backup = manager.backup(resolve_url_from_args(args, manager), args.output)
            print(f"Backup written: {backup.bin_path}")
            print(f"Config written: {backup.ini_path}")
            return 0

        if args.command == "write":
            config = load_write_config(args)
            if not args.apply:
                print(preview_write_plan(config))
                return 0
            if not args.yes and not confirm_operation("Write EEPROM changes?"):
                print("Aborted")
                return 1
            url = resolve_url_from_args(args, manager)
            result = manager.write(url, config, manager.default_backup_prefix("write"))
            print(f"Target: {result.url}")
            print(f"Automatic backup: {result.backup.bin_path}")
            print(f"Automatic config backup: {result.backup.ini_path}")
            print(f"Applied {len(result.property_names)} public properties")
            print(f"User Area payload bytes: {result.user_area_length}")
            return 0

        if args.command == "restore":
            if not args.yes and not confirm_operation("Restore raw EEPROM image?"):
                print("Aborted")
                return 1
            backup = manager.restore(resolve_url_from_args(args, manager), args.image, manager.default_backup_prefix("restore"))
            print(f"Automatic backup: {backup.bin_path}")
            print(f"Automatic config backup: {backup.ini_path}")
            print("Raw EEPROM image restored")
            return 0

        if args.command == "restore-config":
            if not args.yes and not confirm_operation("Restore EEPROM settings from INI? User Area will not be restored."):
                print("Aborted")
                return 1
            backup = manager.restore_config(
                resolve_url_from_args(args, manager),
                args.ini_file,
                manager.default_backup_prefix("restore-config"),
            )
            print(f"Automatic backup: {backup.bin_path}")
            print(f"Automatic config backup: {backup.ini_path}")
            print("INI configuration restored (User Area unchanged)")
            return 0

        if args.command == "udev":
            config = load_config(args.config)
            written_files = write_udev_bundle(config, args.output)
            for path in written_files:
                print(path)
            print("")
            print("Next step:")
            print(render_install_hint(args.output))
            return 0

        raise CliValidationError(f"Unsupported command: {args.command}")
    except (CliValidationError, ConfigValidationError, DeviceSelectionError, EepromManagerError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def confirm_operation(prompt: str) -> bool:
    answer = input(f"{prompt} [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _parse_override_value(raw_value: str) -> Any:
    text = raw_value.strip()
    if text == "":
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text