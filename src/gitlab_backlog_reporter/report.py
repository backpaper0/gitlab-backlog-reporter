"""バックログを Markdown のレポートにする。"""

from dataclasses import dataclass
from datetime import date

from gitlab_backlog_reporter.backlog import PeriodBacklog, Sprint, backlog_state, is_status_label
from gitlab_backlog_reporter.gitlab import Json


@dataclass(frozen=True)
class ReportContext:
    host: str
    group: str
    today: date


def render(backlog: PeriodBacklog, context: ReportContext) -> str:
    sections = [_header(backlog, context), *_warnings(backlog.warnings), _summary(backlog), _backlog_list(backlog)]
    return "\n\n".join(sections) + "\n"


def _header(backlog: PeriodBacklog, context: ReportContext) -> str:
    period = backlog.period
    period_cell = (
        f"`{period.prefix}`（{_date_range(period.start, period.end)}、{len(period.sprints)} スプリント）"
    )
    return "\n".join(
        [
            f"# バックログレポート: {context.group} / {period.prefix}",
            "",
            "| 接続先 | group | 期 | 基準日 |",
            "|---|---|---|---|",
            f"| {context.host} | `{context.group}` | {period_cell} | {context.today.isoformat()} |",
        ]
    )


def _warnings(warnings: tuple[str, ...]) -> list[str]:
    if not warnings:
        return []
    return ["\n".join(["> [!WARNING]", *(f"> - {w}" for w in warnings)])]


def _summary(backlog: PeriodBacklog) -> str:
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
            f"| Icebox（open、参考） | {icebox} |",
        ]
    )


def _backlog_list(backlog: PeriodBacklog) -> str:
    sections = ["## バックログ一覧"]
    sections += [_sprint_backlog(sprint, backlog.sprint_backlog(sprint)) for sprint in backlog.period.sprints]
    sections.append(_icebox_backlog(backlog))
    return "\n\n".join(sections)


def _sprint_backlog(sprint: Sprint, issues: tuple[Json, ...]) -> str:
    heading = f"### {sprint.title}（{_date_range(sprint.start, sprint.end)}）"
    rows = [
        f"| {_issue_link(i)} | {_cell(i['title'])} | {backlog_state(i)} | {_assignees(i)} | {_cell(_labels(i))} |"
        for i in issues
    ]
    return "\n\n".join([heading, _table(["issue", "タイトル", "状態", "担当者", "ラベル"], rows)])


def _icebox_backlog(backlog: PeriodBacklog) -> str:
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


def _progress(consumed: int, total: int) -> str:
    if total == 0:
        return "**進捗率 —**"
    return f"**進捗率 {_round_half_up(100 * consumed, total)}%** `{_bar(consumed, total, 20)}`"


def _bar(consumed: int, total: int, width: int) -> str:
    filled = _round_half_up(width * consumed, total)
    return "█" * filled + "░" * (width - filled)


def _round_half_up(numerator: int, denominator: int) -> int:
    return (2 * numerator + denominator) // (2 * denominator)


def _date_range(start: date, end: date) -> str:
    return f"{_month_day(start)}〜{_month_day(end)}"


def _month_day(d: date) -> str:
    return f"{d.month}/{d.day}"
