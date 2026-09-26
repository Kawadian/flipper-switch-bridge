# Flipper Switch Controller

Flipper Zero をUSB接続のNintendo Switch用コントローラーとして動かし、PCからBLE経由で入力状態を送る試作リポジトリです。Switch 2用のPro Controller互換USBモードと、従来のPokkén Pad互換モードがあります。Switch 2実機での新モードの動作はまだ確認待ちです。

## 構成

| ディレクトリ | 単独でできること | 橋渡し時の役割 |
| --- | --- | --- |
| `pc/flipper_link` | BLEでFlipperに10バイトの状態を送る | 映像・音声判定プログラムから呼ぶ |
| `flipper/ble_link.*` | BLEで入力を受け、画面に受信数を表示 | USB側に状態を渡す |
| `flipper/pro_usb.*` | Pro ControllerのUSB認識手順と入力を試す | BLE側の状態をPro形式のUSB HIDにする |
| `flipper/switch_usb.*` | 旧Pokkén Pad形式のUSB入力を試す | 単独で利用できる旧形式のUSB HID |
| `flipper/app.c` | 4モードを選択して試す | BLE→USBの接続 |

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

PCとFlipperは **Bluetooth Low Energy（BLE）** で接続します。FlipperのUSB-C端子はSwitch用なので、PCとの通信用USBケーブルは不要です。Windows PCのBluetoothをオンにし、Flipperの `Settings` → `Bluetooth` もオンにします。PCにリポジトリを取得して、PowerShellで次を実行します。

```bash
git clone https://github.com/Kawadian/flipper-switch-bridge.git
cd flipper-switch-bridge
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\flipper-link.exe scan
```

Flipperで `Apps` → `USB` → `Switch Controller` → `BLE receiver` を選択すると、SwitchなしでBLE接続を試せます。`scan` で表示されたアドレスを使い、PowerShellで次を実行してFlipper画面の受信数を確認します。ペアリングコードがFlipperに表示されたらPC側で承認します。

```powershell
.\.venv\Scripts\flipper-link.exe --address "表示されたアドレス" tap A
.\.venv\Scripts\flipper-link.exe --address "表示されたアドレス" tap LEFT
.\.venv\Scripts\flipper-link.exe --address "表示されたアドレス" hold R 1.5
```

最初の `scan` で1台だけ見つかった場合は `--address` を省略できます。`BLE receiver` で画面の `RX` が増えれば、PC→Flipperの通信はできています。`BLE -> USB` なら、受け取った入力がSwitch向けのUSBコントローラーにも送られます。接続できない場合は `BLE receiver` または `BLE -> USB` が起動中か、両機器のBluetoothがオンかを確認してください。

### 3. Switchに接続する

Switch 2では、本体の「設定 → コントローラーと周辺機器 → Proコントローラーの有線通信」をオンにし、Flipperの `Switch Controller` → `USB Pro (Switch 2)` を選びます。FlipperのUSB-C端子をデータ通信できるケーブルでドックのUSB-A端子につなぎ、「持ちかた/順番を変える」画面でOKを短押ししてみてください。Flipperの十字キーはSwitchの十字キー（同時押しは斜め入力）、OK短押しはA、OK長押し中はL＋Rとして出力します。`BLE -> USB Pro` でもUSB側は同じPro形式です。初代Switchで従来形式を試す場合は `USB Pokken (legacy)` を使います。

画面の `USB: configured` はSwitchがUSB設定を選択したことだけを表し、コントローラー登録を意味しません。`USB: Pro handshake` はPro形式のUSB応答手順が進んだことを表します。この表示でもアイコンが出ない場合は、Proとしての登録は確認できていません。画面表示と本体の挙動をissueで知らせてください。

PCから操作するときはFlipperで `BLE -> USB Pro` を選び、PCから同じ `flipper-link` コマンドを実行します。BACK長押しでアプリを終了します。新USBモードのSwitch 2実機での認識と入力はまだ未検証です。

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

公式ファームウェア `1.4.3` で、新しいPro USBモードを含む `.fap` のコンパイル・リンク・API参照検査を確認済みです。Switch 2実機での認識・入力はまだ未検証です。USBの識別子、HID記述子、初期化・サブコマンドへの応答はGP2040-CEのSwitch Pro実装に基づきます。ただしFlipperの標準USB HALは制御エンドポイント0のサイズが8バイトで、参照実装の64バイトとは異なります。Switch 2がこの差を許容するか、実機確認が必要です。旧Pokkénモードの割り込みエンドポイントは参照実装どおり64バイトに修正しました。

## 参考実装

- [Flipper公式ファームウェア](https://github.com/flipperdevices/flipperzero-firmware)
- [Switch-Fightstick: Pokkén Pad互換USB記述子](https://github.com/shinyquagsire23/Switch-Fightstick)
- [GP2040-CE: Switch Pro USB実装（MIT）](https://github.com/OpenStickCommunity/GP2040-CE/tree/main/src/drivers/switchpro)
- [Bleak: PC側BLEクライアント](https://bleak.readthedocs.io/en/latest/api/client.html)

このリポジトリのコードはGPL-3.0で公開します。Flipper公式ファームウェアのライセンス表記も維持してください。
