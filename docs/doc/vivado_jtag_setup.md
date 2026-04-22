# Vivado JTAG Setup

1. Linux で `configs/ft4232h_vivado.json` を使って EEPROM を書き込みます。
2. 必要なら Linux 側で udev ルールを生成して適用します。
3. デバイスを Windows に接続します。
4. FTDI 標準ドライバのまま Vivado hw_server で認識を確認します。

Vivado 互換プロファイルでは EEPROM の Manufacturer を `Xilinx` にします。AMD の `program_ftdi` ドキュメントでは、この値を別の文字列にすると Vivado がデバイスを検出しなくなると説明されています。

純正 `program_ftdi` の FT4232H 既定値に合わせる場合、Channel A は D2XX、Channel B/C/D は VCP、drive current は全チャネル 4mA です。このリポジトリの `configs/ft4232h_vivado.json` はその baseline に合わせています。

Windows でこの baseline を再現するには、D2XX の低レベル `FT_WriteEE` 直書きではなく `eeProgram` / `eeUAWrite` 相当の書き込み経路が必要でした。現在の Windows backend はこの経路を使うため、repo の `write` でも純正 `program_ftdi` と同じ `hw_server` target を再現できます。

User Area には `0x584A0004` の FirmwareId と vendor/product 文字列が書き込まれます。hw_server はこの User Area を見て JTAG デバイスとして識別します。

`Connect FTDI Device` ダイアログの `Product` 表示は、EEPROM の Description ではなく D2XX の live な interface description を表示することがあります。たとえば FT4232H では `Quad RS232-HS A` のように見える場合があります。

AMD guide には未使用チャネルの port setting を FT_PROG で変更できるとあります。現在の Windows backend を `eeProgram` / `eeUAWrite` ベースに揃えたあと、今回の FT4232H 実機では `Channel B driver` を VCP から D2XX に変えても `hw_server` target が維持されることを確認しました。したがって Ch A を JTAG 用、Ch B を D2XX/SPI 用として併用できます。
