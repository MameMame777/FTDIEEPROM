# Base Instructions

- Keep FT4232H hardware constraints explicit in code and validation.
- Treat User Area handling as high risk until verified on real hardware.
- Keep pyftdi private API usage isolated to one module.
- Prefer fail-safe device selection when multiple adapters are attached.
- Keep Linux udev generation deterministic and idempotent.
