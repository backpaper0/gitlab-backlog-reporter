"""期のスプリントと Icebox を選び、対象バックログを集計する。"""

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from gitlab_backlog_reporter.errors import ReportError
from gitlab_backlog_reporter.gitlab import Json

MAX_UNASSIGNED_LINKS = 5
"""割り当てのない issue の警告にリンクを出す件数。"""


BACKLOG_STATES = ("open", "ready", "doing", "review", "close")
"""バックログ状態。遷移する順に並べる。"""

_STATUS_LABELS = {f"status::{state}": state for state in ("ready", "doing", "review")}


def is_status_label(label: str) -> bool:
    """バックログ状態を表す `status::` scoped label か。"""
    return label.startswith("status::")


def backlog_state(issue: Json) -> str:
    """close 済みなら、`status::*` label が残っていても close とする。"""
    if is_consumed(issue):
        return "close"
    return next((_STATUS_LABELS[label] for label in issue["labels"] if label in _STATUS_LABELS), "open")


@dataclass(frozen=True)
class Sprint:
    id: int
    title: str
    start: date
    end: date

    def status(self, today: date) -> str:
        """今日から見たスプリントの状況。開始日と終了日は期間に含む。"""
        if today > self.end:
            return "終了"
        if today < self.start:
            return "未来"
        return "進行中"


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

    def current_sprint(self, today: date) -> Sprint | None:
        """今日が期間に入るスプリント。重なっていれば、先に始まるほうを選ぶ。"""
        return next((s for s in self.sprints if s.start <= today <= s.end), None)


@dataclass(frozen=True)
class BreakdownRow:
    """内訳の1行。name が None の行は、ラベルや担当者がないバックログをまとめたもの。"""

    name: str | None
    total: int
    consumed: int

    @property
    def remaining(self) -> int:
        return self.total - self.consumed


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

    @property
    def total(self) -> int:
        return len(self.targets)

    @property
    def consumed(self) -> int:
        """消化されたバックログの件数。"""
        return sum(1 for issue in self.targets if is_consumed(issue))

        return consumed_count(self.targets)

    @property
    def remaining(self) -> int:
        return self.total - self.consumed

    def by_label(self) -> tuple[BreakdownRow, ...]:
        """`status::*` 以外のラベル別の内訳。"""
        return _breakdown(self.targets, lambda i: (label for label in i["labels"] if not label.startswith("status::")))

    def by_assignee(self) -> tuple[BreakdownRow, ...]:
        """担当者（username）別の内訳。"""
        return _breakdown(self.targets, lambda i: (a["username"] for a in i["assignees"]))


    def sprint_targets(self, sprint: Sprint) -> tuple[Json, ...]:
        """スプリントに割り当てられたバックログ。project、iid の順に並べる。"""
        return _by_reference(issue for issue in self.targets if _milestone_id(issue) == sprint.id)

    def assigned_to(self, sprint: Sprint) -> int:
        """sprint に割り当てられた対象バックログの件数（消化済みも含む）。"""
        return len(self.sprint_targets(sprint))

    def state_counts(self) -> dict[str, int]:
        """バックログ状態ごとの件数。BACKLOG_STATES の順に、0件の状態も含めて並べる。"""
        counts = Counter(backlog_state(issue) for issue in self.targets)
        return {state: counts[state] for state in BACKLOG_STATES}


def is_consumed(issue: Json) -> bool:
    return bool(issue["state"] == "closed")


def _breakdown(issues: Iterable[Json], names_of: Callable[[Json], Iterable[str]]) -> tuple[BreakdownRow, ...]:
    """名前ごとに数える。名前が複数あるバックログはそれぞれに数え、ないものは最後の None の行にまとめる。

    None の行は、件数が 0 なら省く。ただし、ほかの行もなければ 0 件の行として残す。
    """
    totals: Counter[str | None] = Counter()
    consumed: Counter[str | None] = Counter()
    for issue in issues:
        names: set[str | None] = set(names_of(issue)) or {None}
        totals.update(names)
        if is_consumed(issue):
            consumed.update(names)
    rows = [BreakdownRow(n, totals[n], consumed[n]) for n in sorted(n for n in totals if n is not None)]
    if None in totals or not rows:
        rows.append(BreakdownRow(None, totals[None], consumed[None]))
    return tuple(rows)


def consumed_count(issues: tuple[Json, ...]) -> int:
    """消化されたバックログの件数。"""
    return sum(1 for issue in issues if is_consumed(issue))


def select_period(
    milestones: list[Json], prefix: str, excludes: tuple[str, ...], group: str
) -> tuple[Period, list[str]]:
    """名前が prefix で始まり、除外 prefix のどれでも始まらない group milestone をスプリントとして選ぶ。state は問わない。

    何も除外しなかった除外 prefix は警告にする。
    """
    matched = [m for m in milestones if m["title"].startswith(prefix)]
    if not matched:
        names = ", ".join(sorted(m["title"] for m in milestones)) or "（なし）"
        raise ReportError(
            f'名前が "{prefix}" で始まる group milestone がありません。group "{group}" の milestone: {names}'
        )
    warnings = [
        f'除外 prefix "{e}" は何も除外していません（名前が "{prefix}" で始まる group milestone に該当なし）'
        for e in excludes
        if not any(m["title"].startswith(e) for m in matched)
    ]
    kept = [m for m in matched if not m["title"].startswith(excludes)]
    if not kept:
        names = ", ".join(sorted(m["title"] for m in matched))
        raise ReportError(f'名前が "{prefix}" で始まる group milestone は、すべて除外 prefix で除外されました: {names}')
    _check_dates(kept)
    sprints = [
        Sprint(m["id"], m["title"], date.fromisoformat(m["start_date"]), date.fromisoformat(m["due_date"]))
        for m in kept
    ]
    sprints.sort(key=lambda s: (s.start, s.end, s.title))
    return Period(prefix, tuple(sprints)), warnings


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


def collect_backlog(
    milestones: list[Json], issues: list[Json], prefix: str, excludes: tuple[str, ...], icebox: str, group: str
) -> PeriodBacklog:
    period, warnings = select_period(milestones, prefix, excludes, group)
    sprint_ids = {s.id for s in period.sprints}
    targets = tuple(i for i in issues if _milestone_id(i) in sprint_ids)

    warnings.extend(_schedule_warnings(period))
    if not targets:
        warnings.append("対象バックログが 0件です")
    icebox_milestone = next((m for m in milestones if m["title"] == icebox), None)
    icebox_open_issues = None
    if icebox_milestone is None:
        warnings.append(f'Icebox の group milestone "{icebox}" が見つかりません')
    else:
        icebox_open_issues = _by_reference(
            i for i in issues if _milestone_id(i) == icebox_milestone["id"] and i["state"] == "opened"
        )
    warnings.extend(_unassigned_warnings(issues))
    return PeriodBacklog(period, targets, icebox_open_issues, icebox, tuple(warnings))


def _schedule_warnings(period: Period) -> list[str]:
    """スプリントの隙間と重なり。重なりはペアごとに出す。スプリントの長さは問わない。"""
    warnings = []
    sprints = period.sprints
    latest = sprints[0]  # それまでのスプリントのうち、いちばん遅く終わるもの
    for i, sprint in enumerate(sprints[1:], start=1):
        for earlier in sprints[:i]:
            if sprint.start <= earlier.end:
                warnings.append(f"スプリントの期間が重なっています: {_span(earlier)}と {_span(sprint)}")
        if sprint.start > latest.end + timedelta(days=1):
            warnings.append(f"スプリントの間に隙間があります: {_span(latest)}と {_span(sprint)}")
        if sprint.end > latest.end:
            latest = sprint
    return warnings


def _span(sprint: Sprint) -> str:
    return f"{sprint.title}（{sprint.start.month}/{sprint.start.day}〜{sprint.end.month}/{sprint.end.day}）"


def _unassigned_warnings(issues: list[Json]) -> list[str]:
    """milestone がないか project milestone に付いている open の issue。ほかの group milestone と close 済みは数えない。"""
    unassigned = sorted(
        (i for i in issues if i["state"] == "opened" and (i["milestone"] is None or "project_id" in i["milestone"])),
        key=_reference_key,
    )
    if not unassigned:
        return []
    links = ", ".join(f"[{i['references']['full']}]({i['web_url']})" for i in unassigned[:MAX_UNASSIGNED_LINKS])
    rest = len(unassigned) - MAX_UNASSIGNED_LINKS
    more = f" ほか {rest} 件" if rest > 0 else ""
    return [
        f"期のスプリントにも Icebox にも割り当てられていない open の issue が {len(unassigned)} 件あります: {links}{more}"
    ]


def _by_reference(issues: Iterable[Json]) -> tuple[Json, ...]:
    """project、iid の順に並べる。"""
    return tuple(sorted(issues, key=_reference_key))


def _reference_key(issue: Json) -> tuple[str, int]:
    project, iid = issue["references"]["full"].rsplit("#", 1)
    return project, int(iid)


def _milestone_id(issue: Json) -> int | None:
    milestone = issue["milestone"]
    return milestone["id"] if milestone else None
