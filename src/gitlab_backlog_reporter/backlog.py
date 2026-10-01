"""期のスプリントと Icebox を選び、対象バックログを集計する。"""

from dataclasses import dataclass
from datetime import date
from gitlab_backlog_reporter.errors import ReportError
from gitlab_backlog_reporter.gitlab import Json


@dataclass(frozen=True)
class Sprint:
    id: int
    title: str
    start: date
    end: date


@dataclass(frozen=True)
class Period:
    prefix: str
    sprints: tuple[Sprint, ...]

    @property
    def start(self) -> date:
        return min(s.start for s in self.sprints)

    @property
    def end(self) -> date:
        return max(s.end for s in self.sprints)


@dataclass(frozen=True)
class PeriodBacklog:
    """1つの期について集計したバックログ。"""

    period: Period
    targets: tuple[Json, ...]
    """対象バックログ。"""
    icebox_open: int | None
    """Icebox にある open のバックログの件数。Icebox が見つからなければ None。"""
    warnings: tuple[str, ...]

    @property
    def total(self) -> int:
        return len(self.targets)

    @property
    def consumed(self) -> int:
        """消化されたバックログの件数。"""
        return sum(1 for issue in self.targets if issue["state"] == "closed")

    @property
    def remaining(self) -> int:
        return self.total - self.consumed


def select_period(milestones: list[Json], prefix: str, group: str) -> Period:
    """名前が prefix で始まる group milestone をスプリントとして選ぶ。state は問わない。"""
    matched = [m for m in milestones if m["title"].startswith(prefix)]
    if not matched:
        names = ", ".join(sorted(m["title"] for m in milestones)) or "（なし）"
        raise ReportError(
            f'名前が "{prefix}" で始まる group milestone がありません。group "{group}" の milestone: {names}'
        )
    _check_dates(matched)
    sprints = [
        Sprint(m["id"], m["title"], date.fromisoformat(m["start_date"]), date.fromisoformat(m["due_date"]))
        for m in matched
    ]
    sprints.sort(key=lambda s: (s.start, s.end, s.title))
    return Period(prefix, tuple(sprints))


def _check_dates(milestones: list[Json]) -> None:
    missing = sorted(m["title"] for m in milestones if not m["start_date"] or not m["due_date"])
    reversed_ = sorted(
        m["title"]
        for m in milestones
        if m["start_date"] and m["due_date"] and m["start_date"] > m["due_date"]
    )
    messages = []
    if missing:
        messages.append(f"開始日か終了日がないスプリントがあります: {', '.join(missing)}")
    if reversed_:
        messages.append(f"開始日が終了日より後のスプリントがあります: {', '.join(reversed_)}")
    if messages:
        raise ReportError(*messages)


def collect_backlog(milestones: list[Json], issues: list[Json], prefix: str, icebox: str, group: str) -> PeriodBacklog:
    period = select_period(milestones, prefix, group)
    sprint_ids = {s.id for s in period.sprints}
    targets = tuple(i for i in issues if _milestone_id(i) in sprint_ids)

    warnings = []
    if not targets:
        warnings.append("対象バックログが 0件です")
    icebox_milestone = next((m for m in milestones if m["title"] == icebox), None)
    icebox_open = None
    if icebox_milestone is None:
        warnings.append(f'Icebox の group milestone "{icebox}" が見つかりません')
    else:
        icebox_open = sum(
            1 for i in issues if _milestone_id(i) == icebox_milestone["id"] and i["state"] == "opened"
        )
    return PeriodBacklog(period, targets, icebox_open, tuple(warnings))


def _milestone_id(issue: Json) -> int | None:
    milestone = issue["milestone"]
    return milestone["id"] if milestone else None
