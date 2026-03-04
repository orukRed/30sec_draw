# 30秒ドローイングタイマー

お絵描き練習用のカウントダウンタイマーです。  
描画時間・インターバル・セット数を自由に設定して繰り返し練習できます。

---

## 機能

- **常に最前面表示** — お絵描きソフトの上に重ねて使えます
- **描画時間の設定** — 30秒〜300秒（30秒刻み）
- **インターバルの設定** — 1秒〜10秒（1秒刻み）
- **セット数の設定** — 1〜20セット
- **通知音** — 描画時間終了時に Windows システム音で通知（外部ファイル不要）
- **設定の自動保存** — ウィンドウを閉じても設定値を記憶

## 操作

| ボタン | 動作 |
|---|---|
| ▶ 開始 | タイマーをスタート |
| ⏸ 一時停止 / ▶ 再開 | 残り時間を保持したまま停止・再開 |
| ⏭ スキップ | 現在のフェーズ（描画またはインターバル）をスキップ |
| ⏹ 停止 | タイマーをリセットして最初の状態に戻す |

## 画面表示について

| 色 | 状態 |
|---|---|
| 赤 | 描画中 |
| 青 | インターバル中 |
| オレンジ | 一時停止中 |
| 緑 | 全セット完了 |

---

## 使い方

### Python から直接実行

```
python timer.py
```

### exe を使う

`dist\30sec_draw.exe` をダブルクリックするだけで起動できます。  
`30sec_draw.exe` と同じフォルダに `config.json` が自動生成され、設定が保存されます。

---

## exe のビルド方法

このプロジェクトでは [PyInstaller](https://pyinstaller.org/) を使って単一の実行ファイルを生成します。通常は付属の PowerShell スクリプト `build.ps1` を使いますが、そちらが動かない場合や手動で実行したい場合は以下の手順を参照してください。

### 事前準備

```powershell
pip install pyinstaller
```

### ビルド実行

#### 1. スクリプトを使う（推奨）

```powershell
.\build.ps1
```

内部では PyInstaller を探して以下のようなコマンドを実行します：

```powershell
pyinstaller --noconfirm --onefile --windowed --name 30sec_draw timer.py
```

または Python 実行ファイルが環境に応じて `python -m PyInstaller` を使う場合もあります。

#### 2. 直接コマンドを叩く（スクリプトが動作しない時）

```powershell
pyinstaller --noconfirm --onefile --windowed --name 30sec_draw timer.py
```

あるいは Python モジュールとして実行する：

```powershell
python -m PyInstaller --noconfirm --onefile --windowed --name 30sec_draw timer.py
```

上記のいずれかで成功すれば、作業ディレクトリに `dist\30sec_draw.exe` が生成されます。ビルドが失敗する場合はエラーメッセージを確認し、PyInstaller のインストールやパス設定を見直してください。

---

## ファイル構成

```
30sec_draw/
├── timer.py       # メインスクリプト
├── build.ps1      # exe ビルド用スクリプト
├── config.json    # 設定ファイル（自動生成・.gitignore 対象）
└── dist/
    └── 30sec_draw.exe  # 実行ファイル（ビルド後に生成）
```

## 動作環境

- Windows 10 / 11
- Python 3.10 以上（exe 版は Python 不要）
