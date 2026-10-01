"""バックログを Markdown のレポートにする。"""

from dataclasses import dataclass
from datetime import date

from gitlab_backlog_reporter.backlog import PeriodBacklog


@dataclass(frozen=True)
class ReportContext:
    host: str
    group: str
    today: date


def render(backlog: PeriodBacklog, context: ReportContext) -> str:
    sections = [_header(backlog, context), *_warnings(backlog.warnings), _summary(backlog)]
    return "\n\n".join(sections) + "\n"


def _header(backlog: PeriodBacklog, context: ReportContext) -> str:
    period = backlog.period
    period_cell = (
        f"`{period.prefix}`（{_month_day(period.start)}〜{_month_day(period.end)}、{len(period.sprints)} スプリント）"
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


def _progress(consumed: int, total: int) -> str:
    if total == 0:
        return "**進捗率 —**"
    return f"**進捗率 {_round_half_up(100 * consumed, total)}%** `{_bar(consumed, total, 20)}`"


def _bar(consumed: int, total: int, width: int) -> str:
    filled = _round_half_up(width * consumed, total)
    return "█" * filled + "░" * (width - filled)


def _round_half_up(numerator: int, denominator: int) -> int:
    return (2 * numerator + denominator) // (2 * denominator)


def _month_day(d: date) -> str:
    return f"{d.month}/{d.day}"
