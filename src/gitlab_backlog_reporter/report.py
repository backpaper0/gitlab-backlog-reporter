"""バックログを Markdown のレポートにする。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, tzinfo
from decimal import Decimal

from gitlab_backlog_reporter.backlog import (
    BreakdownRow,
    Sprint,
    TargetBacklog,
    TargetSprints,
    backlog_state,
    consumed_count,
    is_status_label,
)
from gitlab_backlog_reporter.burndown import Burndown, build_burndown
from gitlab_backlog_reporter.gitlab import Json, Scope

BURNDOWN_NOTE = (
    "※ 3本の線は、すべて実行時点の割り当てから計算しています。"
    "スプリント間で移したバックログや、途中で追加したバックログは、過去の点にもさかのぼって反映されます"
    "（理想線の始点と予定線の段差は、当時の計画とは異なる場合があります）。"
)


@dataclass(frozen=True)
class ReportContext:
    host: str
    scope: Scope
    today: date
    tz: tzinfo
    show_warnings: bool = True
    """レポートに warning のブロックを書くか。"""
    show_icebox_list: bool = True
    """バックログ一覧に Icebox のセクションを書くか。"""


def render(backlog: TargetBacklog, context: ReportContext) -> str:
    burndown = build_burndown(backlog, context.today, context.tz)
    sections = [
        _header(backlog, context),
        *(_warnings(backlog.warnings) if context.show_warnings else []),
        _summary(backlog, burndown, context.today),
        _burndown(backlog, burndown),
        _backlog_states(backlog),
        _sprint_summary(backlog, context.today),
        _breakdown(backlog),
        _backlog_list(backlog, context.show_icebox_list),
    ]
    return "\n\n".join(sections) + "\n"


def _header(backlog: TargetBacklog, context: ReportContext) -> str:
    target_sprints = backlog.target_sprints
    scope = context.scope
    target_sprints_cell = f"`{target_sprints.prefix}`（{_period_range(target_sprints.start, target_sprints.end)}、{len(target_sprints.sprints)} スプリント）"
    return "\n".join(
        [
            f"# バックログレポート: {scope.full_path} / {target_sprints.prefix}",
            "",
            "| 接続先 | 集計範囲 | 対象スプリント | 基準日 |",
            "|---|---|---|---|",
            f"| {context.host} | `{scope.full_path}`（{scope.kind}） | {target_sprints_cell} | {context.today.isoformat()} |",
        ]
    )


def _warnings(warnings: tuple[str, ...]) -> list[str]:
    if not warnings:
        return []
    return ["\n".join(["> [!WARNING]", *(f"> - {w}" for w in warnings)])]


def _summary(backlog: TargetBacklog, burndown: Burndown, today: date) -> str:
    total = backlog.total
    icebox = "—" if backlog.icebox_open is None else str(backlog.icebox_open)
    return "\n".join(
        [
            "## サマリー",
            "",
            f"{_progress(backlog.consumed, total)} {backlog.consumed} / {total} 件",
            "",
            "| 指標 | 件数 |",
            "|---|---:|",
            f"| 対象バックログ | {total} |",
            f"| 消化 | {backlog.consumed} |",
            f"| 残り（今日） | **{backlog.remaining}** |",
            f"| 予定線の今日の値 | {_number(burndown.planned_today)} |",
            f"| 理想線の今日の値 | {_number(burndown.ideal_today)} |",
            f"| Icebox（open、参考） | {icebox} |",
            "",
            f"現在のスプリント: {_current_sprint(backlog.target_sprints, today)}",
        ]
    )


def _current_sprint(target_sprints: TargetSprints, today: date) -> str:
    sprint = target_sprints.current_sprint(today)
    if sprint is not None:
        return f"**{sprint.title}**（{_period_range(sprint.start, sprint.end)}）"
    if today < target_sprints.start:
        return "なし（集計期間の開始前）"
    if today > target_sprints.end:
        return "なし（集計期間の終了後）"
    return "なし"


def _backlog_states(backlog: TargetBacklog) -> str:
    counts = backlog.state_counts()
    return "\n".join(
        [
            "## バックログ状態",
            "",
            f"| {' | '.join(counts)} | 計 |",
            "|---:" * (len(counts) + 1) + "|",
            f"| {' | '.join(str(n) for n in counts.values())} | {backlog.total} |",
        ]
    )


def _sprint_summary(backlog: TargetBacklog, today: date) -> str:
    rows = []
    for sprint in backlog.target_sprints.sprints:
        issues = backlog.sprint_targets(sprint)
        total = len(issues)
        consumed = consumed_count(issues)
        progress = "—" if total == 0 else f"`{_bar(consumed, total, 10)}` {_percent(consumed, total)}%"
        rows.append(
            f"| {sprint.title} | {_period_range(sprint.start, sprint.end)} | {sprint.status(today)}"
            f" | {total} | {consumed} | {progress} |"
        )
    return "\n".join(
        [
            "## スプリント別サマリー",
            "",
            "| スプリント | 期間 | 状況 | 件数 | 消化 | 進捗率 |",
            "|---|---|---|---:|---:|---|",
            *rows,
        ]
    )


def _breakdown(backlog: TargetBacklog) -> str:
    return "\n".join(
        [
            "## 内訳",
            "",
            "### ラベル別",
            "",
            "| ラベル | 件数 | 消化 | 進捗率 |",
            "|---|---:|---:|---:|",
            *(
                f"| {_row_name(r, lambda n: _cell(f'`{n}`'))} | {r.total} | {r.consumed} | {_percent_cell(r.consumed, r.total)} |"
                for r in backlog.by_label()
            ),
            "",
            "### 担当者別",
            "",
            "| 担当者 | 件数 | 消化 | 残り |",
            "|---|---:|---:|---:|",
            *(
                f"| {_row_name(r, lambda n: f'@{n}')} | {r.total} | {r.consumed} | {r.remaining} |"
                for r in backlog.by_assignee()
            ),
            "",
            "※ 担当者が複数いるバックログは、それぞれの担当者に数えています。",
        ]
    )


def _row_name(row: BreakdownRow, decorate: Callable[[str], str]) -> str:
    return "（なし）" if row.name is None else decorate(row.name)


def _percent_cell(consumed: int, total: int) -> str:
    return "—" if total == 0 else f"{_percent(consumed, total)}%"


def _backlog_list(backlog: TargetBacklog, show_icebox: bool) -> str:
    sections = ["## バックログ一覧"]
    sections += [_sprint_backlog(sprint, backlog.sprint_targets(sprint)) for sprint in backlog.target_sprints.sprints]
    if show_icebox:
        sections.append(_icebox_backlog(backlog))
    return "\n\n".join(sections)


def _sprint_backlog(sprint: Sprint, issues: tuple[Json, ...]) -> str:
    heading = f"### {sprint.title}（{_period_range(sprint.start, sprint.end)}）"
    rows = [
        f"| {_issue_link(i)} | {_cell(i['title'])} | {backlog_state(i)} | {_assignees(i)} | {_cell(_labels(i))} |"
        for i in issues
    ]
    return "\n\n".join([heading, _table(["issue", "タイトル", "状態", "担当者", "ラベル"], rows)])


def _icebox_backlog(backlog: TargetBacklog) -> str:
    heading = "### Icebox（open、参考）"
    if backlog.icebox_open_issues is None:
        return "\n\n".join([heading, f'milestone "{backlog.icebox}" が見つかりません'])
    rows = [f"| {_issue_link(i)} | {_cell(i['title'])} |" for i in backlog.icebox_open_issues]
    return "\n\n".join([heading, _table(["issue", "タイトル"], rows)])


def _table(columns: list[str], rows: list[str]) -> str:
    if not rows:
        return "（なし）"
    return "\n".join(["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns), *rows])


def _cell(text: str) -> str:
    """表のセルを区切らないよう `|` をエスケープする。"""
    return text.replace("|", "\\|")


def _issue_link(issue: Json) -> str:
    return f"[{issue['references']['relative']}]({issue['web_url']})"


def _assignees(issue: Json) -> str:
    return ", ".join(f"@{a['username']}" for a in issue["assignees"]) or "—"


def _labels(issue: Json) -> str:
    return " ".join(f"`{label}`" for label in issue["labels"] if not is_status_label(label)) or "—"


def _burndown(backlog: TargetBacklog, burndown: Burndown) -> str:
    if backlog.total == 0:
        return "## バーンダウン\n\n対象バックログがないため、バーンダウンは表示しません"
    labels = ", ".join(f'"{_month_day(p)}"' for p in burndown.points)
    lines = [
        "## バーンダウン",
        "",
        "```mermaid",
        "---",
        "config:",
        "  xyChart:",
        "    xAxis:",
        "      labelRotation: -45",
        "  themeVariables:",
        "    xyChart:",
        '      plotColorPalette: "#9e9e9e, #1f77b4, #d62728"',
        "---",
        "xychart-beta",
        f'  title "{backlog.target_sprints.prefix} バーンダウン"',
        f'  x-axis "週" [{labels}]',
        f'  y-axis "残件数" 0 --> {backlog.total}',
        f'  line "理想" {_series(burndown.ideal)}',
        f'  line "予定" {_series(burndown.planned)}',
    ]
    legend = ["凡例: 灰 = 理想 / 青 = 予定 / 赤 = 実績"]
    if burndown.actual:
        lines.append(f'  line "実績" {_series(burndown.actual)}')
    else:
        legend += ["", "集計期間が始まる前のため、実績線はありません"]
    lines += ["```", "", *legend, "", BURNDOWN_NOTE]
    return "\n".join(lines)


def _series(values: tuple[Decimal, ...] | tuple[int, ...]) -> str:
    return "[" + ", ".join(_number(v) for v in values) + "]"


def _number(value: Decimal | int) -> str:
    """小数第1位までの値を、整数なら小数点なしで書く。"""
    return str(value).removesuffix(".0")


def _progress(consumed: int, total: int) -> str:
    if total == 0:
        return "**進捗率 —**"
    return f"**進捗率 {_percent(consumed, total)}%** `{_bar(consumed, total, 20)}`"


def _percent(consumed: int, total: int) -> int:
    return _round_half_up(100 * consumed, total)


def _bar(consumed: int, total: int, width: int) -> str:
    filled = _round_half_up(width * consumed, total)
    return "█" * filled + "░" * (width - filled)


def _round_half_up(numerator: int, denominator: int) -> int:
    return (2 * numerator + denominator) // (2 * denominator)


def _period_range(start: date, end: date) -> str:
    return f"{_month_day(start)}〜{_month_day(end)}"


def _month_day(d: date) -> str:
    return f"{d.month}/{d.day}"
