"""バックログを Markdown のレポートにする。"""

from dataclasses import dataclass
from datetime import date, tzinfo
from decimal import Decimal

from gitlab_backlog_reporter.backlog import PeriodBacklog
from gitlab_backlog_reporter.burndown import Burndown, build_burndown

BURNDOWN_NOTE = (
    "※ 3本の線は、すべて実行時点の割り当てから計算しています。"
    "スプリント間で移したバックログや、途中で追加したバックログは、過去の点にもさかのぼって反映されます"
    "（理想線の始点と予定線の段差は、当時の計画とは異なる場合があります）。"
)


@dataclass(frozen=True)
class ReportContext:
    host: str
    group: str
    today: date
    tz: tzinfo


def render(backlog: PeriodBacklog, context: ReportContext) -> str:
    burndown = build_burndown(backlog, context.today, context.tz)
    sections = [
        _header(backlog, context),
        *_warnings(backlog.warnings),
        _summary(backlog, burndown),
        _burndown(backlog, burndown),
    ]
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


def _summary(backlog: PeriodBacklog, burndown: Burndown) -> str:
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
        ]
    )


def _burndown(backlog: PeriodBacklog, burndown: Burndown) -> str:
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
        f'  title "{backlog.period.prefix} バーンダウン"',
        f'  x-axis "週" [{labels}]',
        f'  y-axis "残件数" 0 --> {backlog.total}',
        f'  line "理想" {_series(burndown.ideal)}',
        f'  line "予定" {_series(burndown.planned)}',
    ]
    if burndown.actual:
        lines.append(f'  line "実績" {_series(burndown.actual)}')
    lines += ["```", "", "凡例: 灰 = 理想 / 青 = 予定 / 赤 = 実績"]
    if not burndown.actual:
        lines += ["", "期が始まる前のため、実績線はありません"]
    lines += ["", BURNDOWN_NOTE]
    return "\n".join(lines)


def _series(values: tuple[Decimal, ...] | tuple[int, ...]) -> str:
    return "[" + ", ".join(_number(v) for v in values) + "]"


def _number(value: Decimal | int) -> str:
    """小数第1位までの値を、整数なら小数点なしで書く。"""
    return str(value).removesuffix(".0")


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
