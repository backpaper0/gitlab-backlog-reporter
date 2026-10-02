"""期の対象バックログのバーンダウン（理想線、予定線、実績線）を計算する。

日付 D の点は「D の 00:00 時点に残っている件数」を表す。
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from gitlab_backlog_reporter.backlog import PeriodBacklog


@dataclass(frozen=True)
class SprintLoad:
    """1つのスプリントに割り当てられたバックログの件数（close 済みも含む）と、その期間。"""

    count: int
    start: date
    end: date


@dataclass(frozen=True)
class Burndown:
    points: tuple[date, ...]
    ideal: tuple[Decimal, ...]
    planned: tuple[Decimal, ...]
    actual: tuple[int, ...]
    """今日までの点の実績。今日が期の始まりより前なら空。"""
    ideal_today: Decimal
    planned_today: Decimal


def weekly_points(start: date, end: date) -> list[date]:
    """start から7日ごとの点を打ち、end の翌日の点で終える。"""
    finish = end + timedelta(days=1)
    points = []
    d = start
    while d < finish:
        points.append(d)
        d += timedelta(days=7)
    points.append(finish)
    return points


def ideal_at(total: int, start: date, finish: date, t: date) -> Fraction:
    """start で total、finish で 0 になる直線の、t での値。"""
    return total * _remaining_ratio(start, finish, t)


def planned_at(sprints: Iterable[SprintLoad], t: date) -> Fraction:
    """各スプリントの件数が、そのスプリントの期間中に一定の速さで消化されるとしたときの、t での残り。"""
    return sum((s.count * _remaining_ratio(s.start, s.end + timedelta(days=1), t) for s in sprints), Fraction(0))


def actual_at(total: int, closed_on: Iterable[date], d: date) -> int:
    """d より前に close されたものを除いた残り。"""
    return total - sum(1 for c in closed_on if c < d)


def round1(x: Fraction) -> Decimal:
    """小数第1位で四捨五入する。"""
    return (Decimal(x.numerator) / Decimal(x.denominator)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def build_burndown(backlog: PeriodBacklog, today: date, tz: tzinfo) -> Burndown:
    period = backlog.period
    total = backlog.total
    points = weekly_points(period.start, period.end)
    start, finish = points[0], points[-1]
    loads = _sprint_loads(backlog)
    closed_on = [_local_date(i["closed_at"], tz) for i in backlog.targets if i["closed_at"]]
    return Burndown(
        points=tuple(points),
        ideal=tuple(round1(ideal_at(total, start, finish, p)) for p in points),
        planned=tuple(round1(planned_at(loads, p)) for p in points),
        actual=tuple(actual_at(total, closed_on, p) for p in points if p <= today),
        ideal_today=round1(ideal_at(total, start, finish, today)),
        planned_today=round1(planned_at(loads, today)),
    )


def _sprint_loads(backlog: PeriodBacklog) -> Sequence[SprintLoad]:
    return [SprintLoad(backlog.assigned_to(s), s.start, s.end) for s in backlog.period.sprints]


def _local_date(timestamp: str, tz: tzinfo) -> date:
    return datetime.fromisoformat(timestamp).astimezone(tz).date()


def _remaining_ratio(start: date, finish: date, t: date) -> Fraction:
    """start で 1、finish で 0 になる直線の t での値を、0 から 1 の範囲に収めたもの。"""
    ratio = Fraction((finish - t).days, (finish - start).days)
    return min(max(ratio, Fraction(0)), Fraction(1))
