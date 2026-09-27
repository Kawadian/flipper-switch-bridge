# Flipper Switch Controller

Flipper Zero をUSB接続のNintendo Switch用コントローラーとして動かし、PCからBLE経由で入力状態を送る試作リポジトリです。Switch 2用のPro Controller互換USBモードと、従来のPokkén Pad互換モードがあります。Switch 2実機でPro USB入力が反映されることを確認しました。BLE通信の実機確認は進行中です。

## 構成

| ディレクトリ | 単独でできること | 橋渡し時の役割 |
| --- | --- | --- |
| `pc/flipper_link` | BLEでFlipperに10バイトの状態を送る | 映像・音声判定プログラムから呼ぶ |
| `flipper/ble_link.*` | BLEで入力を受け、画面に受信数を表示 | USB側に状態を渡す |
| `flipper/pro_protocol.*` | Pro ControllerのUSB初期化・ペアリング応答を単体で検証する | USBデバイス側の応答データを作る |
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

**WindowsのBluetooth設定で通常の `Flipper ...` を接続しただけでは、入力は送れません。** アプリ起動中に別のBLE機器名 `SwitchLink ...` が現れ、`flipper-link` コマンドが接続と送信を担当します。Windows設定画面でペアリング済みの機器が一時的に「接続済み」となってすぐ切れても、それだけでは通信エラーとは判断できません。通常の `Flipper ...` のペアリングは残して構いません。

```bash
git clone https://github.com/Kawadian/flipper-switch-bridge.git
cd flipper-switch-bridge
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Flipperで `Apps` → `USB` → `Switch Controller` → `BLE receiver` を選択すると、SwitchなしでBLE接続を試せます。**この版の `.fap` に更新してから** `scan` を再実行し、表示された `SwitchLink ...` のアドレスを使います。最初に `probe` で10秒間接続し、Flipper画面の `BLE: connected` と `RX` の増加を確認します。ペアリングコードがFlipperに表示されたらPC側で承認します。

```powershell
.\.venv\Scripts\flipper-link.exe scan
.\.venv\Scripts\flipper-link.exe --address "表示されたアドレス" probe 10
.\.venv\Scripts\flipper-link.exe --address "表示されたアドレス" tap A
.\.venv\Scripts\flipper-link.exe --address "表示されたアドレス" tap LEFT
.\.venv\Scripts\flipper-link.exe --address "表示されたアドレス" hold R 1.5
```

`scan` で1台だけ見つかった場合は `--address` を省略できます。`probe` 中は接続を保ち、正常終了すると切断します。`tap` と `hold` もコマンド終了後に切断する仕様です。`BLE receiver` で画面の `RX` が増えれば、PC→Flipperの通信はできています。`BLE -> USB Pro` なら、受け取った入力がSwitch向けのUSBコントローラーにも送られます。`SwitchLink ...` が見つからない場合は、新しい `.fap`、モード起動、両機器のBluetooth設定を確認してください。

### 3. Switchに接続する

Switch 2では、本体の「設定 → コントローラーと周辺機器 → Proコントローラーの有線通信」をオンにし、Flipperの `Switch Controller` → `USB Pro (Switch 2)` を選びます。FlipperのUSB-C端子をデータ通信できるケーブルでドックのUSB-A端子につなぎ、「持ちかた/順番を変える」画面でOKを短押ししてみてください。Flipperの十字キーはSwitchの十字キー（同時押しは斜め入力）、OK短押しはA、OK長押し中はL＋Rとして出力します。`BLE -> USB Pro` でもUSB側は同じPro形式です。初代Switchで従来形式を試す場合は `USB Pokken (legacy)` を使います。

画面の `USB: configured` はSwitchがUSB設定を選択したことだけを表し、コントローラー登録を意味しません。`USB: Pro handshake` はPro形式のUSB応答手順が進んだことを表します。`RX 01:01 pair:02` のような表示は最後に受信したUSBレポート・コマンドとペアリングの進行段階です。エラーが続く場合は再接続を繰り返さず、USBケーブルを外した後の表示をissueで知らせてください。

PCから操作するときはFlipperで `BLE -> USB Pro` を選び、PCから同じ `flipper-link` コマンドを実行します。動作中にBACKを押すとUSB接続を解除してアプリを終了します。Pro USBモードのSwitch 2実機での入力は確認済みです。BLE経由での入力は実機確認待ちです。

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
flipper-link --address <表示されたアドレス> probe 10
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
cc -std=c11 -Wall -Wextra -Werror tests/pro_protocol_test.c flipper/pro_protocol.c -o /tmp/pro_protocol_test
/tmp/pro_protocol_test
```

旧版のPro USBモードをSwitch 2に接続すると、ユーザーの実機で2162-0002のエラーが発生しました。有線接続中のBluetoothペアリングコマンドへ内容のない応答を返すと同じエラーを起こすという互換実装の記録を基に、MAC・キー・保存通知の応答を追加しました。USB切替コマンドへの不要な応答と、接続直後の一方的な識別応答も止めています。修正版でSwitch 2実機への入力が反映されることを確認しました。

Flipperの標準USB HALは制御エンドポイント0を8バイトで初期化しますが、Proモードの間だけ参照実装と同じ64バイトに設定し、アプリ終了時に戻します。旧Pokkénモードの割り込みエンドポイントは参照実装どおり64バイトです。

## 参考実装

- [Flipper公式ファームウェア](https://github.com/flipperdevices/flipperzero-firmware)
- [Switch-Fightstick: Pokkén Pad互換USB記述子](https://github.com/shinyquagsire23/Switch-Fightstick)
- [GP2040-CE: Switch Pro USB実装（MIT）](https://github.com/OpenStickCommunity/GP2040-CE/tree/main/src/drivers/switchpro)
- [Karakuri firmware: Switch 2有線Pro応答の調査・実装](https://github.com/eggletric/karakuri-firmware/blob/main/firmware/pico_switch_pad/procon_usb.h)
- [Bleak: PC側BLEクライアント](https://bleak.readthedocs.io/en/latest/api/client.html)

このリポジトリのコードはGPL-3.0で公開します。Flipper公式ファームウェアのライセンス表記も維持してください。
