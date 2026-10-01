"""期のスプリントと Icebox を選び、対象バックログを集計する。"""

from dataclasses import dataclass
from datetime import date, timedelta
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

    warnings = _schedule_warnings(period)
    icebox_milestone = next((m for m in milestones if m["title"] == icebox), None)
    icebox_open = None
    if icebox_milestone is None:
        warnings.append(f'Icebox の group milestone "{icebox}" が見つかりません')
    else:
        icebox_open = sum(
            1 for i in issues if _milestone_id(i) == icebox_milestone["id"] and i["state"] == "opened"
        )
    warnings.extend(_unassigned_warning(issues))
    return PeriodBacklog(period, targets, icebox_open, tuple(warnings))


def _schedule_warnings(period: Period) -> list[str]:
    """スプリントの隙間と重なり。スプリントの長さは問わない。"""
    warnings = []
    latest = period.sprints[0]  # それまでのスプリントのうち、いちばん遅く終わるもの
    for sprint in period.sprints[1:]:
        if sprint.start <= latest.end:
            warnings.append(f"スプリントの期間が重なっています: {_span(latest)}と {_span(sprint)}")
        elif sprint.start > latest.end + timedelta(days=1):
            warnings.append(f"スプリントの間に隙間があります: {_span(latest)}と {_span(sprint)}")
        if sprint.end > latest.end:
            latest = sprint
    return warnings


def _span(sprint: Sprint) -> str:
    return f"{sprint.title}（{sprint.start.month}/{sprint.start.day}〜{sprint.end.month}/{sprint.end.day}）"


UNASSIGNED_LINKS = 5


def _unassigned_warning(issues: list[Json]) -> list[str]:
    """milestone がないか project milestone に付いている open の issue。ほかの group milestone と close 済みは数えない。"""
    unassigned = sorted(
        (i for i in issues if i["state"] == "opened" and (i["milestone"] is None or "project_id" in i["milestone"])),
        key=_reference_key,
    )
    if not unassigned:
        return []
    links = ", ".join(f"[{i['references']['full']}]({i['web_url']})" for i in unassigned[:UNASSIGNED_LINKS])
    rest = len(unassigned) - UNASSIGNED_LINKS
    more = f" ほか {rest} 件" if rest > 0 else ""
    return [
        f"期のスプリントにも Icebox にも割り当てられていない open の issue が {len(unassigned)} 件あります: {links}{more}"
    ]


def _reference_key(issue: Json) -> tuple[str, int]:
    project, iid = issue["references"]["full"].rsplit("#", 1)
    return project, int(iid)


def _milestone_id(issue: Json) -> int | None:
    milestone = issue["milestone"]
    return milestone["id"] if milestone else None
