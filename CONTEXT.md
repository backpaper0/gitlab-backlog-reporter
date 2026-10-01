# GitLab Backlog Reporter

GitLab の group 上で運用されるアジャイル開発のバックログとスプリントを読み取り、進捗を可視化するレポートを作るためのコンテキスト。

## Language

**バックログ**:
GitLab の issue 1件で表される作業単位。必ずいずれかのスプリントか Icebox に割り当てられる。
_Avoid_: チケット, タスク, ストーリー

**スプリント**:
名前が期の prefix（例: `Iteration-Q3-`）で始まり、開始日と終了日を持つ group milestone。期間は2週間。名前の大文字と小文字は区別する。milestone 自体の open / closed は問わない。
_Avoid_: イテレーション（GitLab の Iterations 機能と紛らわしいため）

**期**:
名前に共通の prefix を持つスプリントのまとまり。1つのレポートは1つの期を扱う。期の長さ（四半期か半期か）は運用で決まる。
_Avoid_: クォーター, 上期, 下期（長さを含意するため）

**Icebox**:
まだスプリント計画に乗っていないバックログの置き場となる group milestone。名前の完全一致で1つ指定し、日付を持たない。全期で共有するか期ごとに分けるかは運用で決まる。

**バックログ状態**:
バックログが遷移する5つの状態: open → ready → doing → review → close。ready / doing / review は `status::` scoped label で表し、open / close は issue の state で表す。

**消化**:
バックログが close されたこと。close の理由は問わない。
_Avoid_: 完了, Done

**進捗率**:
対象バックログのうち消化されたものの割合（件数ベース）。

**対象バックログ**:
1つのレポートが集計するバックログの集合。1つの group 配下の全 project の issue からなる。

