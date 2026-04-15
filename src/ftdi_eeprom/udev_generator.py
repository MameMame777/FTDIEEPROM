from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .config_loader import validate_config


def generate_udev_bundle(config: Mapping[str, Any]) -> dict[str, str]:
    validate_config(config)
    return {
        "90-ftdi-permissions.rules": build_permissions_rules(config),
        "91-ftdi-unbind.rules": build_unbind_rules(config),
        "92-ftdi-actions.rules": build_actions_rules(config),
        "ftdi-unbind.sh": build_unbind_script(config),
        "install-udev.sh": build_install_script(config),
    }


def write_udev_bundle(config: Mapping[str, Any], output_dir: str | Path) -> list[Path]:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, content in generate_udev_bundle(config).items():
        path = target_dir / name
        path.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def render_install_hint(output_dir: str | Path) -> str:
    output_path = Path(output_dir)
    return f"cd {output_path}\nsudo ./install-udev.sh"


def build_permissions_rules(config: Mapping[str, Any]) -> str:
    udev = config["udev"]
    device = config["device"]
    conditions = [
        'SUBSYSTEM=="usb"',
        'ENV{DEVTYPE}=="usb_device"',
        f'ATTR{{idVendor}}=="{_hex4(device["vendor_id"])}"',
        f'ATTR{{idProduct}}=="{_hex4(device["product_id"])}"',
    ]
    product = str(device.get("product", "")).strip()
    if product:
        conditions.append(f'ATTR{{product}}=="{product}"')
    conditions.append(f'GROUP="{udev["group"]}"')
    conditions.append(f'MODE="{udev["mode"]}"')
    return "\n".join(
        [
            "# Auto-generated FT4232H permission rule",
            "# USB device node match: ENV{DEVTYPE} with direct ATTR lookups",
            ", ".join(conditions),
            "",
        ]
    )


def build_unbind_rules(config: Mapping[str, Any]) -> str:
    udev = config["udev"]
    device = config["device"]
    base_conditions = [
        'ACTION=="add"',
        'SUBSYSTEM=="usb"',
        'ENV{DEVTYPE}=="usb_interface"',
        'DRIVER=="ftdi_sio"',
        f'ATTRS{{idVendor}}=="{_hex4(device["vendor_id"])}"',
        f'ATTRS{{idProduct}}=="{_hex4(device["product_id"])}"',
    ]
    product = str(device.get("product", "")).strip()
    if product:
        base_conditions.append(f'ATTRS{{product}}=="{product}"')

    lines = [
        "# Auto-generated FT4232H unbind rules",
        "# USB interface node match: ENV{DEVTYPE} with parent ATTRS lookups and direct interface ATTR",
    ]
    for interface in config["udev"]["unbind_interfaces"]:
        conditions = base_conditions + [
            f'ATTR{{bInterfaceNumber}}=="{interface}"',
            f'RUN+="{udev["script_path"]} %k"',
        ]
        lines.append(", ".join(conditions))
    lines.append("")
    return "\n".join(lines)


def build_actions_rules(config: Mapping[str, Any]) -> str:
    _ = config
    return "\n".join(
        [
            "# Auto-generated FT4232H post-action rules",
            "# Reserved for local customization such as symlink creation or notifications.",
            "",
        ]
    )


def build_unbind_script(config: Mapping[str, Any]) -> str:
    _ = config
    return "\n".join(
        [
            "#!/bin/sh",
            "set -eu",
            "",
            "if [ \"$#\" -lt 1 ]; then",
            "    echo \"usage: $0 <usb-interface-kernel-name>\" >&2",
            "    exit 2",
            "fi",
            "",
            "INTERFACE=\"$1\"",
            "DRIVER_DIR=\"/sys/bus/usb/drivers/ftdi_sio\"",
            "",
            "if [ ! -d \"$DRIVER_DIR\" ]; then",
            "    logger -t ftdi-unbind \"ftdi_sio driver directory not found\"",
            "    exit 0",
            "fi",
            "",
            "if [ ! -e \"$DRIVER_DIR/$INTERFACE\" ]; then",
            "    logger -t ftdi-unbind \"$INTERFACE already unbound\"",
            "    exit 0",
            "fi",
            "",
            "printf '%s' \"$INTERFACE\" > \"$DRIVER_DIR/unbind\"",
            "logger -t ftdi-unbind \"unbound $INTERFACE from ftdi_sio\"",
            "",
        ]
    )


def build_install_script(config: Mapping[str, Any]) -> str:
    udev = config["udev"]
    script_target = udev["script_path"]
    return "\n".join(
        [
            "#!/bin/sh",
            "set -eu",
            "",
            "if [ \"$(id -u)\" -ne 0 ]; then",
            "    echo \"install-udev.sh must be run as root\" >&2",
            "    exit 1",
            "fi",
            "",
            f"RULES_DIR=\"/etc/udev/rules.d\"",
            f"SCRIPT_TARGET=\"{script_target}\"",
            f"GROUP_NAME=\"{udev['group']}\"",
            "SCRIPT_DIR=\"$(dirname \"$SCRIPT_TARGET\")\"",
            "",
            "groupadd -f \"$GROUP_NAME\"",
            "if [ -n \"${SUDO_USER:-}\" ] && [ \"$SUDO_USER\" != \"root\" ]; then",
            "    usermod -aG \"$GROUP_NAME\" \"$SUDO_USER\"",
            "fi",
            "mkdir -p \"$RULES_DIR\"",
            "mkdir -p \"$SCRIPT_DIR\"",
            "install -m 0644 90-ftdi-permissions.rules \"$RULES_DIR/90-ftdi-permissions.rules\"",
            "install -m 0644 91-ftdi-unbind.rules \"$RULES_DIR/91-ftdi-unbind.rules\"",
            "install -m 0644 92-ftdi-actions.rules \"$RULES_DIR/92-ftdi-actions.rules\"",
            "install -m 0755 ftdi-unbind.sh \"$SCRIPT_TARGET\"",
            "udevadm control --reload-rules",
            "udevadm trigger",
            "echo \"Installed FTDI udev rules\"",
            "echo \"  group: $GROUP_NAME\"",
            "if [ -n \"${SUDO_USER:-}\" ] && [ \"$SUDO_USER\" != \"root\" ]; then",
            "    echo \"  user added to group: $SUDO_USER\"",
            "    echo \"  note: re-login may be required for new group membership\"",
            "else",
            "    echo \"  note: add your user to $GROUP_NAME manually if needed\"",
            "fi",
            "echo \"  script: $SCRIPT_TARGET\"",
            "",
        ]
    )


def _hex4(value: int) -> str:
    return f"{int(value):04x}"
