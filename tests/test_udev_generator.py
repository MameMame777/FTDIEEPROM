from __future__ import annotations

from ftdi_eeprom.config_loader import get_default_config, merge_config
from ftdi_eeprom.udev_generator import build_permissions_rules, build_unbind_rules, generate_udev_bundle
from ftdi_eeprom.vivado_config import build_vivado_preset


def test_permissions_rule_uses_usb_device_devtype_and_attr():
    rules = build_permissions_rules(build_vivado_preset())
    assert 'ENV{DEVTYPE}=="usb_device"' in rules
    assert 'ATTR{idVendor}=="0403"' in rules
    assert 'ATTR{idProduct}=="6011"' in rules
    assert 'ATTR{product}=="FT4232H Vivado Bridge"' in rules
    assert 'ATTR{serial}' not in rules


def test_unbind_rule_uses_usb_interface_devtype_and_attrs():
    rules = build_unbind_rules(build_vivado_preset())
    assert 'ENV{DEVTYPE}=="usb_interface"' in rules
    assert 'ATTRS{idVendor}=="0403"' in rules
    assert 'ATTRS{idProduct}=="6011"' in rules
    assert 'ATTRS{product}=="FT4232H Vivado Bridge"' in rules
    assert 'ATTRS{serial}' not in rules
    assert 'ATTR{bInterfaceNumber}=="00"' in rules


def test_unbind_rule_respects_selected_interfaces():
    config = merge_config(get_default_config(), {"udev": {"unbind_interfaces": ["01", "03"]}})
    rules = build_unbind_rules(config)
    assert 'ATTR{bInterfaceNumber}=="01"' in rules
    assert 'ATTR{bInterfaceNumber}=="03"' in rules
    assert 'ATTR{bInterfaceNumber}=="00"' not in rules


def test_generate_bundle_contains_install_script_and_unbind_script():
    bundle = generate_udev_bundle(build_vivado_preset())
    assert "install-udev.sh" in bundle
    assert "ftdi-unbind.sh" in bundle
    assert "/usr/local/bin/ftdi-unbind.sh" in bundle["91-ftdi-unbind.rules"]
    assert 'usermod -aG "$GROUP_NAME" "$SUDO_USER"' in bundle["install-udev.sh"]
