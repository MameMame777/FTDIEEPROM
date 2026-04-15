# FTDI EEPROM Tool

FT4232H の EEPROM を読み書きする Python CLI です。Vivado hw_server が JTAG として認識できる User Area プリセットと、Linux 向け udev ルール生成を含みます。

## Scope

- 対応チップ: FT4232H のみ
- EEPROM 設定書き込み: Linux 実行前提
- Vivado 認識確認: Windows 実機確認前提
- Channel A/B: MPSSE 対応
- Channel C/D: UART only

## Install

```bash
python -m pip install -e .
python -m pip install -e .[dev]
```

## Usage

```bash
python -m ftdi_eeprom read --serial FT4232H0001
python -m ftdi_eeprom backup --serial FT4232H0001 -o backup/current
python -m ftdi_eeprom write --config configs/ft4232h_default.json
python -m ftdi_eeprom write --config configs/ft4232h_default.json --apply --yes --serial FT4232H0001
python -m ftdi_eeprom restore backup/current.bin --apply --yes --serial FT4232H0001
python -m ftdi_eeprom restore-config backup/current.ini --allow-partial --apply --yes --serial FT4232H0001
python -m ftdi_eeprom udev --config configs/ft4232h_default.json -o output/udev
```

`write` はデフォルトで dry-run です。EEPROM を変更するには `--apply` が必要です。

## Device Selection

- `--url`: pyftdi URL を完全指定
- `--serial`: 複数台接続時の個体絞り込み
- `--interface`: 開く interface 番号 (1=A, 2=B, 3=C, 4=D)
- `--url` は `--serial` / `--interface` と同時指定不可
- 複数台接続時に `--serial` も `--url` も無い場合は fail-safe でエラー終了

## Config Files

- [configs/ft4232h_default.json](configs/ft4232h_default.json): 推奨既定プロファイル。Ch A は Vivado 認識用 User Area 付き、Ch B は Linux 側 SPI 用の D2XX、Ch C/D は VCP
- [configs/ft4232h_vivado.json](configs/ft4232h_vivado.json): 全チャネル D2XX の Vivado 寄りプリセット

MPSSE GPIO 初期化値は EEPROM 項目ではありません。`ft4232h_default.json` では B を SPI 用に使う意図を `runtime_profile` で表現しています。

## Vivado Recognition Conditions

Vivado 2024.2 の `scripts/program_ftdi` 配下で確認できる範囲では、FT4232H が Vivado 向けとして扱われるための主要条件は次の通りです。

- USB VID/PID が `0x0403:0x6011` であること
- User Area 先頭 4 byte に FT4232H 用 firmware ID `0x584A0004` が入っていること
- User Area が `firmware_id + vendor string + NUL + product string + NUL` の並びで書かれていること
- Windows 側で D2XX ドライバ経由で開けること

このリポジトリの `ft4232h_default.json` と `ft4232h_vivado.json` は、上記のソフトウェア側条件を満たすように実装しています。`write --config ... --apply` では EEPROM の公開プロパティに加えて Vivado 用 User Area payload も書き込みます。

ただし、最終的な認識可否は Windows 実機での確認が必要です。Vivado / hw_server 側の最終判定は Tcl だけでは完結せず、D2XX ドライバ状態や実機の再列挙結果にも依存します。

## Linux udev

生成コマンド:

```bash
python -m ftdi_eeprom udev --config configs/ft4232h_default.json -o output/udev
```

配置手順:

```bash
cd output/udev
sudo ./install-udev.sh
```

`install-udev.sh` は `sudo` で実行された場合、`SUDO_USER` を `FPGAuser` へ自動追加します。新しい group 反映には再ログインが必要です。

ルール配置先:

- `/etc/udev/rules.d/90-ftdi-permissions.rules`
- `/etc/udev/rules.d/91-ftdi-unbind.rules`
- `/etc/udev/rules.d/92-ftdi-actions.rules`
- `/usr/local/bin/ftdi-unbind.sh` など `udev.script_path` で指定した完全パス

生成ルールのマッチ条件:

- `90-ftdi-permissions.rules`: `VID/PID + product` 一致で USB device ノードに権限付与
- `91-ftdi-unbind.rules`: `VID/PID + product + bInterfaceNumber` 一致で `ftdi_sio` を unbind
- `serial` は udev ルールのマッチ条件には使いません

このため、同じ `product` 文字列を持つ FT4232H には同じルールが適用されます。個体単位で分けたい場合は `product` 文字列を分ける前提です。

追加で必要なコマンド:

```bash
sudo groupadd -f FPGAuser
sudo udevadm control --reload-rules
sudo udevadm trigger
```

`sudo` ではなく root 直実行した場合や、追加対象ユーザーを明示したい場合は手動で実行します。

```bash
sudo usermod -aG FPGAuser <username>
```

## Known Limitations

- User Area round-trip は pyftdi private API 依存のため、実機での Phase 0 検証が必要です。
- pyftdi のデバイス列挙や interface オープンの挙動は環境差があるため、複数台接続時は `--serial` 指定を推奨します。
- Linux udev は distro/kernel 差分があります。`RUN=` 実行、`DRIVER=="ftdi_sio"`、`udevadm trigger` の挙動は実環境で確認してください。

## License

This project is released under the MIT License. See [LICENSE](LICENSE).

## Trademark Notice

FTDI, Xilinx, and Vivado are trademarks or registered trademarks of their respective owners. They are referenced here only to describe hardware and software compatibility, and this repository does not include vendor source code from those products.

## References

- [docs/doc/vivado_jtag_setup.md](docs/doc/vivado_jtag_setup.md)
- [docs/doc/windows_driver_matrix.md](docs/doc/windows_driver_matrix.md)
