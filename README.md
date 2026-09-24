# Flipper Switch Controller

Flipper Zero を、USB接続のNintendo Switch用コントローラーとして動かし、PCからBLE経由で入力状態を送る試作リポジトリです。対象は初代Nintendo Switchのドック接続です。Switch 2は未検証です。

## 構成

| ディレクトリ | 単独でできること | 橋渡し時の役割 |
| --- | --- | --- |
| `pc/flipper_link` | BLEでFlipperに10バイトの状態を送る | 映像・音声判定プログラムから呼ぶ |
| `flipper/ble_link.*` | BLEで入力を受け、画面に受信数を表示 | USB側に状態を渡す |
| `flipper/switch_usb.*` | FlipperのOKでSwitchのAを押す | BLE側の状態をUSB HIDにする |
| `flipper/app.c` | 3モードを選択して試す | BLE→USBの接続 |

USBの低レベル関数は外部アプリ（FAP）向けSDKに公開されていないため、Flipper側は**公式ファームウェアに組み込んでビルド**します。PC側は通常のPythonパッケージです。純正ファームウェアへの変更はアプリの追加だけで、既存のUSBモードをアプリ終了時に復元します。

## Flipper側のビルド

公式ファームウェアの検証済みコミット `7f0b6e1c14431708cfde75ae1ba13df59e868041` を取得します。初回ビルドで公式のツールチェーンがダウンロードされます。

```bash
git clone --recursive https://github.com/flipperdevices/flipperzero-firmware.git
cd flipperzero-firmware
git checkout 7f0b6e1c14431708cfde75ae1ba13df59e868041
git submodule update --init --recursive
cd ..
python3 scripts/install_into_firmware.py ./flipperzero-firmware
cd flipperzero-firmware
./fbt updater_package
```

`updater_package` が生成した更新パッケージを、公式の更新手順でFlipperに適用します。初回はUSB単体で試せます。FlipperをSwitchドックのUSB-Aポートにつなぎ、`Switch Controller` → `USB gamepad` → OK。Switchで「設定 → コントローラーとセンサー → Proコントローラーの有線通信」をオンにして、FlipperのOKを押してA入力を確認します。BACK長押しで終了します。

BLE単体を試すときは `BLE receiver`、両方を接続するときは `BLE -> USB` を選びます。BLE接続状態と受信件数がFlipperに表示されます。なおFlipperのUSB端子をSwitchに使っている間、PCへのUSBデバッグ接続はできません。

## PC側

WindowsのBluetoothが利用できる環境で実行します。

```bash
python -m venv .venv
python -m pip install -e .
flipper-link scan
flipper-link --address <表示されたアドレス> tap A
flipper-link --address <表示されたアドレス> hold LEFT 1.5
```

FlipperはBLE接続時に画面でペアリングコードの確認を求める場合があります。複数のFlipperが検出されたら `--address` を指定してください。`scan` と `BLE receiver` モードならSwitchなしでBLEの接続と受信を確認できます。映像認識側からは `ControllerLink.connect()` と `send(ControllerState(...))` を使えます。

```python
import asyncio
from flipper_link.ble import ControllerLink
from flipper_link.protocol import Button, ControllerState

async def main():
    async with ControllerLink.connect() as link:
        await link.hold(ControllerState(buttons=Button.A), 0.1)

asyncio.run(main())
```

状態パケットは `[version=1, sequence, buttons_le16, hat, lx, ly, rx, ry, xor]` の10バイトです。`hat=8`、各スティック`128`が中立。BLE通信が切れた場合や500ms以上入力が途絶えた場合は、Flipperが入力を中立に戻します。PCは押下を維持するとき100ms間隔で状態を再送します。終了時も中立状態を送ります。

## 確認状況

Pythonのパケット符号化・復号、CRC相当のXOR検査、および構文検査はローカルで確認できます。

```bash
python -m unittest discover -s tests -v
```

上記コミットの公式ファームウェアに組み込み、コンパイル・リンクまで確認済みです。実機Switchでの認識・A入力はまだ未検証です。USB識別子とHIDレポートは既存のHORI Pokkén Pad互換実装の形式を基にしています。接続環境やSwitch本体の設定によって追加調整が必要になる場合があります。

## 参考実装

- [Flipper公式ファームウェア](https://github.com/flipperdevices/flipperzero-firmware)
- [Switch-Fightstick: Pokkén Pad互換USB記述子](https://github.com/shinyquagsire23/Switch-Fightstick)
- [Bleak: PC側BLEクライアント](https://bleak.readthedocs.io/en/latest/api/client.html)

このリポジトリのコードはGPL-3.0で公開します。Flipper公式ファームウェアのライセンス表記も維持してください。
