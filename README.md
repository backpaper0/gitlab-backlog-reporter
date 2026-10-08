# gitlab-backlog-reporter

GitLab の group のバックログとスプリントの進捗を Markdown のレポートにする。用語は [CONTEXT.md](CONTEXT.md) を参照。

## インストール

```sh
uv tool install git+https://github.com/backpaper0/gitlab-backlog-reporter  # 更新は uv tool upgrade gitlab-backlog-reporter
```

## 使い方

```sh
GITLAB_HOST=https://gitlab.example.com GITLAB_PRIVATE_TOKEN=... gbr colors -o report.md
```

- 位置引数: group の full path（数値だけなら id）
- `-o/--output PATH`: レポートを書くファイル（既存のファイルは上書き）。デフォルトは標準出力
- `--sprint-prefix`: スプリントとする group milestone の名前の prefix（デフォルト `Iteration-`）
- `--exclude-sprint-prefix PREFIX`: スプリントから除外する group milestone の名前の prefix。繰り返し指定できる（例: `--sprint-prefix Iteration- --exclude-sprint-prefix Iteration-3Q-`）
- `--icebox`: Icebox とする group milestone の名前（デフォルト `Icebox`）
- `--no-report-warnings`: レポートに warning を書かない。標準エラー出力には今までどおり書く
- `--no-icebox-list`: バックログ一覧に Icebox のセクションを書かない。サマリーの Icebox の件数は残る
- タイムゾーンはローカルのものを使う。変えたいときは `TZ` 環境変数で指定する

### mise で複数のレポートを管理する

[mise](https://mise.jdx.dev/) の task にすると、group やオプション、接続先の GitLab が違う複数のレポートを1つの `mise.toml` で管理できる。PAT は `.secrets.env` に書き、task の `env` で接続先ごとに渡し分ける。

```sh
# .secrets.env（commit しない。このディレクトリを git で管理するなら .gitignore に入れる）
GITLAB_PRIVATE_TOKEN=...
OTHER_GITLAB_PRIVATE_TOKEN=...
```

```toml
# mise.toml
[env]
_.file = { path = ".secrets.env", redact = true }

[tasks.report-colors]
run = "gbr colors -o colors.md"
env = { GITLAB_HOST = "https://gitlab.example.com" }

[tasks.report-shapes]
run = "gbr shapes --sprint-prefix Iteration-Q3- -o shapes.md"
env = { GITLAB_HOST = "https://gitlab.other.example.com", GITLAB_PRIVATE_TOKEN = "{{ env.OTHER_GITLAB_PRIVATE_TOKEN }}" }
```

`mise run report-colors` で実行する。PAT の変数名（`OTHER_GITLAB_PRIVATE_TOKEN`）は例で、task の `env` から参照できれば何でもよい。

- `run` に `GITLAB_PRIVATE_TOKEN=...` を直接書かない。`mise run` は実行するコマンドを表示するので、PAT がコンソールに出る
- task の `env` にも PAT を直接書かない。コマンドとしては表示されないが、`mise.toml` に平文で残り、redact の対象にもならない。`.secrets.env` から読んだ値は、task の出力に出ても `[redacted]` に置き換わる

## 開発

```sh
uv run pytest                     # テスト
UPDATE_GOLDEN=1 uv run pytest     # golden test の期待ファイル（tests/golden/）を更新する
uv run mypy                       # 型検査
uv run scripts/record_fixtures.py # 例の環境から tests/fixtures/colors/ のスナップショットを取り直す
```

### 例の環境

golden test のスナップショットを取る GitLab（group `colors`、`http://localhost:9080`）を docker compose で立てる。root のパスワードはローカル専用の固定値で、`example/root_password` にある。

```sh
docker compose -f example/compose.yaml up -d --wait  # 起動（初回は数分かかる）
uv run scripts/seed_example.py                       # データを投入し、root の token を example/.token に保存する
GITLAB_HOST=http://localhost:9080 GITLAB_PRIVATE_TOKEN=$(cat example/.token) uv run gbr colors
```

`seed_example.py` は group `colors` がすでにあるとエラーで止まる。立て直すときは `docker compose -f example/compose.yaml down -v` からやり直す。
