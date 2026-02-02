
# 山手線ゲーム (GUI)

簡単に遊べる山手線ゲームのデスクトップ GUI アプリです。プレイヤーは順番にお題（地名や人名など）を入力し、既出やルール違反を自動判定しながら進行します。

## 主な特徴
- GUI（`PySide6` ベース）による直感的な操作
- タイマー機能・得点管理
- 重複入力・不正解の自動判定
- CSV 形式でお題リストを追加・編集可能（`data/answer_list/`）

## 使用技術
- Python 3.8 以上（3.8～3.11 での動作確認を推奨）
- GUI: `PySide6`（コードは `PySide6` の import を前提としています）

## セットアップ（ローカル）
1. リポジトリをクローンします。

```bash
git clone https://github.com/Akapaprika/YamanoteLineGame
cd YamanoteLineGame
```

2. 仮想環境を作成してアクティベートし、依存をインストールします（例、Windows PowerShell）:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt  # なければ `pip install PySide6` を実行
```

（推奨）プロジェクトに `requirements.txt` を追加する場合は最低限 `PySide6` を記載してください。

## 実行方法
- 直接起動（現状の構成で動く確実な方法）:

```powershell
python src\main.py
```

- パッケージ化された実行（`python -m src`）について:
    `src/__main__.py` はパッケージ実行を想定した相対 import を用いていますが、現状 `src/__init__.py` が存在しないため `python -m src` は失敗します。`python -m src` を使いたい場合は、`src/__init__.py` を追加するか、パッケージとしてインストールしてください。

## CSV（お題）フォーマットの注意
- 実装は単純な「1 行 = 1 件」に限定していません。`src/model/answer_list.py` の実装に従うと、1 行は「表示（display）とマッチ（match）の交互ペア」で構成されます（例: `表示1,マッチ1,表示2,マッチ2,...`）。
- 空行は「未回答（前半）／回答済（後半）」の区切りとして使われます（保存機能もこのルールに従います）。
- 重要: 各表示に対応する「match」（判定に用いる正規化済みの文字列）が必須です。行内に display/match の対が無い場合、その行は無視されます。詳しくは `src/model/answer_list.py` を参照してください。

（補足）ユーザ操作としては「1 行 1 件」に揃えると管理が簡単ですが、実装的には複数ペアを同一行に並べることも可能です。

## 音声ファイル（秒読み・効果音）について
- 秒読み・効果音の対応は `src/config.py` の `COUNTDOWN_SOUNDS` と `SOUND_CORRECT` / `SOUND_WRONG` で設定されています。必要に応じてファイル名と秒数の対応を修正してください。

## 設定
- `src/config.py` にタイマーや音声ファイルパス等の設定があります。必要に応じて編集してください。

## 開発・貢献
- バグ報告や機能リクエストは GitHub Issues へお願いします。
- プルリクエストの流れ:
    1. フォーク
    2. ブランチ作成（feature/xxxx）
    3. 変更をコミットして PR 作成

## 公開（GitHub に上げる際の注意）
- ソースコード自体はルートの `LICENSE` に MIT ライセンスを記載しています（コードは MIT で公開可能）。
- ただし `data/` 以下の音声や外部データの権利は個別に確認してください。権利の問題がある素材は除外して公開してください。

## 開発者向けメモ
- エントリポイント: `src/main.py` の `run()` 関数
- GUI コンポーネント: `src/ui/`、ゲームロジック: `src/controller/game_controller.py`、データ処理: `src/model/answer_list.py`
