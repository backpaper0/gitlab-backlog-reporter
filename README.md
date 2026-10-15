# gitlab-backlog-reporter

GitLab の group か project のバックログとスプリントの進捗を Markdown のレポートにする。group なら group milestone、project なら project milestone をスプリントと Icebox として集計する。用語は [CONTEXT.md](CONTEXT.md) を参照。

## インストール

```sh
uv tool install git+https://github.com/backpaper0/gitlab-backlog-reporter  # 更新は uv tool upgrade gitlab-backlog-reporter
```

## 使い方

```sh
GITLAB_HOST=https://gitlab.example.com GITLAB_PRIVATE_TOKEN=... gbr colors -o report.md

# project を集計範囲にする（project milestone をスプリントと Icebox にする）
GITLAB_HOST=https://gitlab.example.com GITLAB_PRIVATE_TOKEN=... gbr --project colors/red -o report.md
```

- 位置引数: 集計範囲の full path（数値だけなら id）。`--project` を付けなければ group、付ければ project
- `--project`: 位置引数を project として解釈し、その project の issue と project milestone だけを集計する。祖先の group の group milestone はスプリントにも Icebox にもならない
- `-o/--output PATH`: レポートを書くファイル（既存のファイルは上書き）。デフォルトは標準出力
- `--sprint-prefix`: スプリントとする、集計範囲の milestone の名前の prefix（デフォルト `Iteration-`）
- `--exclude-sprint-prefix PREFIX`: スプリントから除外する、集計範囲の milestone の名前の prefix。繰り返し指定できる（例: `--sprint-prefix Iteration- --exclude-sprint-prefix Iteration-3Q-`）
- `--icebox`: Icebox とする、集計範囲の milestone の名前（デフォルト `Icebox`）
- `--no-report-warnings`: レポートに warning を書かない。標準エラー出力には今までどおり書く
- `--no-icebox-list`: バックログ一覧に Icebox のセクションを書かない。サマリーの Icebox の件数は残る
- `--holidays PATH`: 休業日（土日以外の休日）を書いたファイル。スプリントの隙間が休日（土日と休業日）だけなら警告しない。指定しなければ、休日は土日だけ
- タイムゾーンはローカルのものを使う。変えたいときは `TZ` 環境変数で指定する

### 休業日のファイル

UTF-8 で、1行に1日付を `YYYY-MM-DD` で書く。空行は読み飛ばし、`#` から行末まではコメントになる。祝日も会社が定めた休みも、休みにしたい日はここに書く。

```
# 2026 年
2026-01-01  # 元日
2026-01-12  # 成人の日
2026-12-29  # 年末年始休業
```

- 土日の日付、重複した日付、期の外の日付を書いてもかまわない。何年分を1つのファイルに書いてもよい
- 解釈できない日付がある、またはファイルを読めないときは、レポートを書かずにエラー終了する

### mise で複数のレポートを管理する

[mise](https://mise.jdx.dev/) の task にすると、集計範囲やオプション、接続先の GitLab が違う複数のレポートを1つの `mise.toml` で管理できる。PAT は `.secrets.env` に書き、task の `env` で接続先ごとに渡し分ける。

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
run = "gbr colors --holidays holidays.txt -o colors.md"
env = { GITLAB_HOST = "https://gitlab.example.com" }

[tasks.report-shapes]
run = "gbr shapes --sprint-prefix Iteration-Q3- --holidays holidays.txt -o shapes.md"
env = { GITLAB_HOST = "https://gitlab.other.example.com", GITLAB_PRIVATE_TOKEN = "{{ env.OTHER_GITLAB_PRIVATE_TOKEN }}" }
```

`mise run report-colors` で実行する。PAT の変数名（`OTHER_GITLAB_PRIVATE_TOKEN`）は例で、task の `env` から参照できれば何でもよい。休業日のファイル（`holidays.txt`）は `mise.toml` と同じディレクトリに置き、複数のレポートで共有する。

- `run` に `GITLAB_PRIVATE_TOKEN=...` を直接書かない。`mise run` は実行するコマンドを表示するので、PAT がコンソールに出る
- task の `env` にも PAT を直接書かない。コマンドとしては表示されないが、`mise.toml` に平文で残り、redact の対象にもならない。`.secrets.env` から読んだ値は、task の出力に出ても `[redacted]` に置き換わる

## 開発

```sh
uv run pytest                     # テスト
UPDATE_GOLDEN=1 uv run pytest     # golden test の期待ファイル（tests/golden/）を更新する
uv run mypy                       # 型検査
uv run scripts/record_fixtures.py # サンプル GitLab から tests/fixtures/colors/ のスナップショットを取り直す
```

### サンプル GitLab

golden test のスナップショットを取るための GitLab を、サンプル GitLab と呼ぶ。そこに投入する group `colors` のデータを、サンプルデータと呼ぶ。サンプル GitLab（`http://localhost:9080`）は docker compose で立てる。root のパスワードはローカル専用の固定値で、`example/root_password` にある。

```sh
docker compose -f example/compose.yaml up -d --wait  # 起動（初回は数分かかる）
uv run scripts/seed_example.py                       # データを投入し、root の token を example/.token に保存する
GITLAB_HOST=http://localhost:9080 GITLAB_PRIVATE_TOKEN=$(cat example/.token) uv run gbr colors
```

`seed_example.py` は group `colors` がすでにあるとエラーで止まる。立て直すときは `docker compose -f example/compose.yaml down -v` からやり直す。
