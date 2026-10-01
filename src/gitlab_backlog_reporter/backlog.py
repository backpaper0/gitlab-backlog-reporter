"""期のスプリントと Icebox を選び、対象バックログを集計する。"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Literal

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
    icebox_open_issues: tuple[Json, ...] | None
    """Icebox にある open のバックログ。project、iid の順に並べる。Icebox が見つからなければ None。"""
    icebox: str
    """Icebox とする group milestone の名前。"""
    warnings: tuple[str, ...]

    @property
    def icebox_open(self) -> int | None:
        """Icebox にある open のバックログの件数。Icebox が見つからなければ None。"""
        return None if self.icebox_open_issues is None else len(self.icebox_open_issues)

    def sprint_backlog(self, sprint: Sprint) -> tuple[Json, ...]:
        """スプリントに割り当てられた対象バックログ。project、iid の順に並べる。"""
        return _by_project_and_iid(i for i in self.targets if _milestone_id(i) == sprint.id)

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
    icebox_milestone = next((m for m in milestones if m["title"] == icebox), None)
    icebox_open_issues = None
    if icebox_milestone is None:
        warnings.append(f'Icebox の group milestone "{icebox}" が見つかりません')
    else:
        icebox_open_issues = _by_project_and_iid(
            i for i in issues if _milestone_id(i) == icebox_milestone["id"] and i["state"] == "opened"
        )
    return PeriodBacklog(period, targets, icebox_open_issues, icebox, tuple(warnings))


type BacklogState = Literal["open", "ready", "doing", "review", "close"]

_LABELED_STATES: tuple[BacklogState, ...] = ("ready", "doing", "review")


def is_status_label(label: str) -> bool:
    """バックログ状態を表す `status::` scoped label か。"""
    return label.startswith("status::")


def backlog_state(issue: Json) -> BacklogState:
    """close は issue の state で、ready / doing / review は `status::` scoped label で決まる。どれでもなければ open。"""
    if issue["state"] == "closed":
        return "close"
    for state in _LABELED_STATES:
        if f"status::{state}" in issue["labels"]:
            return state
    return "open"


def _by_project_and_iid(issues: Iterable[Json]) -> tuple[Json, ...]:
    return tuple(sorted(issues, key=lambda i: (i["references"]["full"].rsplit("#", 1)[0], i["iid"])))


def _milestone_id(issue: Json) -> int | None:
    milestone = issue["milestone"]
    return milestone["id"] if milestone else None
