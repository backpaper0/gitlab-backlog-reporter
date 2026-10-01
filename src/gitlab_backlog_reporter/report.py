"""バックログを Markdown のレポートにする。"""

from dataclasses import dataclass
from datetime import date

from gitlab_backlog_reporter.backlog import Period, PeriodBacklog, consumed_count


@dataclass(frozen=True)
class ReportContext:
    host: str
    group: str
    today: date


def render(backlog: PeriodBacklog, context: ReportContext) -> str:
    sections = [
        _header(backlog, context),
        *_warnings(backlog.warnings),
        _summary(backlog, context.today),
        _backlog_states(backlog),
        _sprint_summary(backlog, context.today),
    ]
    return "\n\n".join(sections) + "\n"


def _header(backlog: PeriodBacklog, context: ReportContext) -> str:
    period = backlog.period
    period_cell = (
        f"`{period.prefix}`（{_period_range(period.start, period.end)}、{len(period.sprints)} スプリント）"
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


def _summary(backlog: PeriodBacklog, today: date) -> str:
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
            "",
            f"現在のスプリント: {_current_sprint(backlog.period, today)}",
        ]
    )


def _current_sprint(period: Period, today: date) -> str:
    sprint = period.current_sprint(today)
    if sprint is not None:
        return f"**{sprint.title}**（{_period_range(sprint.start, sprint.end)}）"
    if today < period.start:
        return "なし（期の開始前）"
    if today > period.end:
        return "なし（期の終了後）"
    return "なし"


def _backlog_states(backlog: PeriodBacklog) -> str:
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


def _sprint_summary(backlog: PeriodBacklog, today: date) -> str:
    rows = []
    for sprint in backlog.period.sprints:
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
