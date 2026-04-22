# Windows Driver Matrix

| Channel | Use on Windows | Driver |
| --- | --- | --- |
| A | Vivado hw_server JTAG / EEPROM access baseline | FTDI standard D2XX driver |
| B | Default UART on pure Vivado baseline | FTDI standard VCP driver |
| C | Default UART on pure Vivado baseline | FTDI standard VCP driver |
| D | Default UART on pure Vivado baseline | FTDI standard VCP driver |

このプロジェクトは Windows では D2XX backend を使うため、FT4232H interface を WinUSB/libusbK に切り替える必要はありません。標準の FTDI driver (`FTDIBUS` / VCP) を維持したまま EEPROM を読み書きできます。

純正 `program_ftdi` で FT4232H を書き込んだ実機では、A は D2XX、B/C/D は VCP の構成で `hw_server` target が列挙されました。repo の Windows writer も `eeProgram` / `eeUAWrite` を使うように揃えたことで、この baseline を再現できることを確認しています。

AMD guide の未使用チャネル変更に関する記述どおり、今回の実機では `Channel B driver` を VCP から D2XX に変更しても target 列挙は維持されました。そのため、repo の split-use profile では EEPROM 側を A=D2XX, B=D2XX, C/D=VCP として扱えます。
