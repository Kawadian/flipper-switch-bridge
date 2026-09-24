# Flipper Switch Controller

Flipper Zero を、USB接続のNintendo Switch用コントローラーとして動かし、PCからBLE経由で入力状態を送る試作リポジトリです。対象は初代Nintendo Switchのドック接続です。Switch 2は未検証です。

## 構成

| ディレクトリ | 単独でできること | 橋渡し時の役割 |
| --- | --- | --- |
| `pc/flipper_link` | BLEでFlipperに10バイトの状態を送る | 映像・音声判定プログラムから呼ぶ |
| `flipper/ble_link.*` | BLEで入力を受け、画面に受信数を表示 | USB側に状態を渡す |
| `flipper/switch_usb.*` | FlipperのOKでSwitchのAを押す | BLE側の状態をUSB HIDにする |
| `flipper/app.c` | 3モードを選択して試す | BLE→USBの接続 |

Flipper側は **`.fap` アプリとして追加できます**。公式ファームウェアのUSB設定切り替えとBluetoothプロファイル／シリアルサービスのAPIを使用し、アプリ終了時に標準の状態へ戻します。PC側は通常のPythonパッケージです。ファームウェア全体を更新する方法も残しています。

## 導入方法

### 1. Flipper用アプリを入手する（推奨）

[GitHub Actions の「Build Flipper app」](https://github.com/Kawadian/flipper-switch-bridge/actions/workflows/build-fap.yml)を開き、`Run workflow` → `main` → `Run workflow` を選びます。`firmware_ref` はFlipperに入っている**公式ファームウェアと同じリリース**を指定します。初期値は `1.4.3` です。完了した実行の `Artifacts` から `switch_controller-fap` をダウンロードし、ZIPを解凍して `switch_controller.fap` を取り出します。

FlipperにmicroSDカードを挿してPCへUSB接続します。[qFlipper](https://docs.flipper.net/zero/qflipper)の `File manager` → `SD Card` で `apps/USB` フォルダを開き、`switch_controller.fap` をアップロードします。フォルダがなければ作成してください。qFlipperから切断すると、Flipperの `Apps` → `USB` → `Switch Controller` から起動できます。**ファームウェアの書き換えは不要**です。

ファームウェアのバージョンが異なってアプリ起動時にAPI互換性のエラーが表示された場合は、Actionsを同じファームウェアのタグ／コミットで再実行し、生成された `.fap` に置き換えてください。カスタムファームウェアのAPI互換性は保証していません。

#### ファームウェア全体を更新する場合（従来の方法）

[GitHub Actions の「Build Flipper firmware」](https://github.com/Kawadian/flipper-switch-bridge/actions/workflows/build-firmware.yml)を開き、`Run workflow` → `main` → `Run workflow` を選びます。完了した実行を開き、画面下部の `Artifacts` から `flipper-switch-update` をダウンロードします。GitHubからダウンロードしたZIPを**一度解凍**すると `flipper-switch-update.tgz` が入っています。Flipperにインストールするファイルは、この `.tgz` です。これは公式ファームウェアをビルドし直して内蔵アプリを追加する方式です。

FlipperをPCへUSB接続し、[qFlipper](https://docs.flipper.net/zero/qflipper)の詳細設定にある `Install from file` で `.tgz` を選びます。現在のファームウェアを書き換えるため、設定を手元にも残したい場合はqFlipperのバックアップ機能で先に保存してください。更新後、Flipperのメニューに `Switch Controller` が現れます。

microSDから更新する場合は `.tgz` を解凍し、内部の `f7-update-*` フォルダをSDカードの `update` フォルダにコピーして、Flipperのファイルブラウザから `update.fuf` を実行します。

### 2. PC側をインストールする

WindowsでBluetoothを使えるPCにリポジトリを取得して、次を実行します。

```bash
git clone https://github.com/Kawadian/flipper-switch-bridge.git
cd flipper-switch-bridge
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\flipper-link.exe scan
```

Flipperで `Switch Controller` → `BLE receiver` を選択すると、SwitchなしでBLE接続を試せます。`scan` で表示されたアドレスを使い、PowerShellで次を実行してFlipper画面の受信数を確認します。

```powershell
.\.venv\Scripts\flipper-link.exe --address "表示されたアドレス" tap A
```

### 3. Switchに接続する

まずFlipperの `Switch Controller` → `USB gamepad` を選び、FlipperのUSB-C端子をデータ通信できるケーブルで初代SwitchのドックのUSB-A端子につなぎます。Switchで「設定 → コントローラーとセンサー → Proコントローラーの有線通信」をオンにして、FlipperのOKボタンでA入力を試します。

PCから操作するときはFlipperで `BLE -> USB` を選び、PCから同じ `flipper-link` コマンドを実行します。BACK長押しでアプリを終了します。実機でのSwitch認識と入力はまだ未検証です。

## Flipper側をローカルでビルドする

### `.fap` アプリをビルドする

Flipperの公式ファームウェアと一致するタグでビルドします。例えば公式リリース `1.4.3` の場合:

```bash
git clone --recursive https://github.com/flipperdevices/flipperzero-firmware.git
cd flipperzero-firmware
git checkout 1.4.3
git submodule update --init --recursive
cd ..
python3 scripts/install_fap.py ./flipperzero-firmware
cd flipperzero-firmware
./fbt fap_switch_controller
```

出力は `build/f7-firmware-D/.extapps/switch_controller.fap` です。初回ビルドでは公式ツールチェーンをダウンロードします。

### ファームウェア全体をビルドする（従来の方法）

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

リポジトリのルートで `python3 scripts/package_update.py flipperzero-firmware/dist --output flipper-switch-update.tgz` を実行すると、同じ形式のインストール用ファイルを作れます。

BLE単体を試すときは `BLE receiver`、両方を接続するときは `BLE -> USB` を選びます。BLE接続状態と受信件数がFlipperに表示されます。なおFlipperのUSB端子をSwitchに使っている間、PCへのUSBデバッグ接続はできません。

## PC側のAPI

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

公式ファームウェア `1.4.3` と上記コミットの両方で、USBとBluetoothを含む `.fap` のコンパイル・リンク・API参照検査を確認済みです。従来の内蔵アプリとしてのファームウェアビルドも確認済みです。実機FlipperでのBLE受信、実機Switchでの認識・A入力はまだ未検証です。USB識別子とHIDレポートは既存のHORI Pokkén Pad互換実装の形式を基にしています。接続環境やSwitch本体の設定によって追加調整が必要になる場合があります。

## 参考実装

- [Flipper公式ファームウェア](https://github.com/flipperdevices/flipperzero-firmware)
- [Switch-Fightstick: Pokkén Pad互換USB記述子](https://github.com/shinyquagsire23/Switch-Fightstick)
- [Bleak: PC側BLEクライアント](https://bleak.readthedocs.io/en/latest/api/client.html)

このリポジトリのコードはGPL-3.0で公開します。Flipper公式ファームウェアのライセンス表記も維持してください。
