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

### 例の環境

golden test のスナップショットを取る GitLab（group `colors`、http://localhost:9080）を docker compose で立てる。root のパスワードはローカル専用の固定値で、`example/root_password` にある。

```sh
docker compose -f example/compose.yaml up -d --wait  # 起動（初回は数分かかる）
uv run scripts/seed_example.py                       # データを投入し、root の token を example/.token に保存する
GITLAB_HOST=http://localhost:9080 GITLAB_PRIVATE_TOKEN=$(cat example/.token) uv run gbr colors
```

`seed_example.py` は group `colors` がすでにあるとエラーで止まる。立て直すときは `docker compose -f example/compose.yaml down -v` からやり直す。
