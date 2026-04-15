# Vivado JTAG Setup

1. Linux で `configs/ft4232h_vivado.json` を使って EEPROM を書き込みます。
2. 必要なら Linux 側で udev ルールを生成して適用します。
3. デバイスを Windows に接続します。
4. FTDI 標準ドライバのまま Vivado hw_server で認識を確認します。

User Area には `0x584A0004` の FirmwareId と vendor/product 文字列が書き込まれます。hw_server はこの User Area を見て JTAG デバイスとして識別します。
