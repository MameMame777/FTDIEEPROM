# FTDI EEPROM Project

- Scope: FT4232H EEPROM read/write tooling with Vivado-compatible preset support.
- Runtime target: Linux for EEPROM programming, Windows for Vivado hw_server verification.
- Critical constraint: pyftdi private API use is isolated to `src/ftdi_eeprom/eeprom_backend.py`.
- Dependency policy: keep `pyftdi==0.55.4` pinned in both `pyproject.toml` and `requirements.txt`.
- Safety policy:
  - dry-run by default
  - `--apply` required for destructive operations
  - automatic backup before write/restore operations
- Hardware constraints:
  - FT4232H channel A/B support MPSSE
  - FT4232H channel C/D are UART-only
- Linux udev generation must keep `ENV{DEVTYPE}` and `ATTR`/`ATTRS` matching separate.
- Do not expand scope to other FTDI chips unless explicitly requested.
