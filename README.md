# gitlab-backlog-reporter

GitLab の group のバックログとスプリントの進捗を Markdown のレポートにする。用語は [CONTEXT.md](CONTEXT.md) を参照。

## 使い方

```sh
GITLAB_HOST=https://gitlab.example.com GITLAB_PRIVATE_TOKEN=... uv run gbr colors -o report.md
```

- 位置引数: group の full path（数値だけなら id）
- `-o/--output PATH`: レポートを書くファイル（既存のファイルは上書き）。デフォルトは標準出力
- `--sprint-prefix`: スプリントとする group milestone の名前の prefix（デフォルト `Iteration-`）
- `--icebox`: Icebox とする group milestone の名前（デフォルト `Icebox`）
- タイムゾーンはローカルのものを使う。変えたいときは `TZ` 環境変数で指定する

## 開発

```sh
uv run pytest                     # テスト
UPDATE_GOLDEN=1 uv run pytest     # golden test の期待ファイル（tests/golden/）を更新する
uv run mypy                       # 型検査
uv run scripts/record_fixtures.py # 例の環境から tests/fixtures/colors/ のスナップショットを取り直す
```
