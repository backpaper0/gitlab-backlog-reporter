# GitLab Backlog Reporter

GitLab の group 上で運用されるアジャイル開発のバックログとスプリントを読み取り、進捗を可視化するレポートを作るためのコンテキスト。

## Language

**バックログ**:
GitLab の issue 1件で表される作業単位。必ずいずれかのスプリントか Icebox に割り当てられる。
_Avoid_: チケット, タスク, ストーリー

**スプリント**:
名前が `Iteration-` で始まり、開始日と終了日を持つ milestone。期間は2週間。
_Avoid_: イテレーション（GitLab の Iterations 機能と紛らわしいため）

**Icebox**:
まだスプリント計画に乗っていないバックログの置き場となる、group にただ1つの milestone。日付を持たない。

**バックログ状態**:
バックログが遷移する5つの状態: open → ready → doing → review → close。ready / doing / review は `status::` scoped label で表し、open / close は issue の state で表す。

**消化**:
バックログが close されたこと。close の理由は問わない。
_Avoid_: 完了, Done

**進捗率**:
対象バックログのうち消化されたものの割合（件数ベース）。

**対象バックログ**:
1つのレポートが集計するバックログの集合。1つの group 配下の全 project の issue からなる。
