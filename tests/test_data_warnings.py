"""どのセクションにも属さない警告: スプリントの隙間と重なり、割り当てのない issue。"""

from datetime import date
from zoneinfo import ZoneInfo

from gitlab_backlog_reporter.cli import RunResult, run
from tests.gitlab_fake import FakeGitLab, Json, make_group, make_issue, make_milestone

TODAY = date(2026, 10, 2)
TZ = ZoneInfo("Asia/Tokyo")
ENV = {"GITLAB_HOST": "http://gitlab.test", "GITLAB_PRIVATE_TOKEN": "secret"}


def gbr(milestones: list[Json], issues: list[Json] | None = None) -> RunResult:
    fake = FakeGitLab(make_group(), [*milestones, make_milestone("Icebox")], issues or [])
    return run(["colors"], ENV, TODAY, TZ, fake.transport())


def warnings(result: RunResult) -> list[str]:
    assert result.exit_code == 0
    lines = result.stderr.splitlines()
    assert all(line.startswith("warning: ") for line in lines)
    return [line.removeprefix("warning: ") for line in lines]


def test_contiguous_sprints_have_no_warning() -> None:
    result = gbr(
        [
            make_milestone("Iteration-1", "2026-10-01", "2026-10-14"),
            make_milestone("Iteration-2", "2026-10-15", "2026-10-28"),
        ]
    )

    assert result.stderr == ""
    assert "[!WARNING]" not in result.stdout


def test_gap_between_sprints_names_both_sprints_with_dates() -> None:
    result = gbr(
        [
            make_milestone("Iteration-2", "2026-10-16", "2026-10-28"),
            make_milestone("Iteration-1", "2026-10-01", "2026-10-14"),
        ]
    )

    assert warnings(result) == [
        "スプリントの間に隙間があります: Iteration-1（10/1〜10/14）と Iteration-2（10/16〜10/28）"
    ]


def test_overlapping_sprints_name_both_sprints_with_dates() -> None:
    result = gbr(
        [
            make_milestone("Iteration-1", "2026-10-01", "2026-10-14"),
            make_milestone("Iteration-2", "2026-10-14", "2026-10-28"),
        ]
    )

    assert warnings(result) == [
        "スプリントの期間が重なっています: Iteration-1（10/1〜10/14）と Iteration-2（10/14〜10/28）"
    ]


def test_sprint_inside_a_long_sprint_overlaps_and_leaves_no_gap() -> None:
    result = gbr(
        [
            make_milestone("Iteration-1", "2026-10-01", "2026-10-31"),
            make_milestone("Iteration-2", "2026-10-05", "2026-10-10"),
            make_milestone("Iteration-3", "2026-10-15", "2026-10-20"),
            make_milestone("Iteration-4", "2026-11-01", "2026-11-14"),
        ]
    )

    assert warnings(result) == [
        "スプリントの期間が重なっています: Iteration-1（10/1〜10/31）と Iteration-2（10/5〜10/10）",
        "スプリントの期間が重なっています: Iteration-1（10/1〜10/31）と Iteration-3（10/15〜10/20）",
    ]


def test_sprint_lengths_are_not_checked() -> None:
    result = gbr(
        [
            make_milestone("Iteration-1", "2026-10-01", "2026-10-07"),
            make_milestone("Iteration-2", "2026-10-08", "2026-11-04"),
            make_milestone("Iteration-3", "2026-11-05", "2026-11-05"),
        ]
    )

    assert result.stderr == ""


def test_gap_and_overlap_warnings_are_listed_in_report() -> None:
    result = gbr(
        [
            make_milestone("Iteration-1", "2026-10-01", "2026-10-14"),
            make_milestone("Iteration-2", "2026-10-10", "2026-10-20"),
            make_milestone("Iteration-3", "2026-10-25", "2026-10-31"),
        ]
    )

    assert (
        "> [!WARNING]\n"
        "> - スプリントの期間が重なっています: Iteration-1（10/1〜10/14）と Iteration-2（10/10〜10/20）\n"
        "> - スプリントの間に隙間があります: Iteration-2（10/10〜10/20）と Iteration-3（10/25〜10/31）\n"
        "\n"
        "## サマリー\n"
    ) in result.stdout


SPRINT = make_milestone("Iteration-1", "2026-10-01", "2026-10-14")


def test_open_issues_without_milestone_or_with_project_milestone_are_warned() -> None:
    project_milestone = make_milestone("Iteration-1", "2026-10-01", "2026-10-14", project_id=1)
    issues = [
        make_issue(None, project="colors/rainbow"),
        make_issue(project_milestone, project="colors/hello"),
    ]

    result = gbr([SPRINT], issues)

    a, b = issues
    assert warnings(result) == [
        "期のスプリントにも Icebox にも割り当てられていない open の issue が 2 件あります: "
        f"[colors/hello#{b['iid']}]({b['web_url']}), [colors/rainbow#{a['iid']}]({a['web_url']})"
    ]
    assert "> - 期のスプリントにも Icebox にも割り当てられていない open の issue が 2 件あります: " in result.stdout


def test_closed_issues_and_other_group_milestones_are_ignored() -> None:
    other_period = make_milestone("Iteration-Q2-6", "2026-09-17", "2026-09-30")
    other_prefix = make_milestone("Release-1")
    issues = [
        make_issue(None, closed_at="2026-10-01T09:00:00.000Z"),
        make_issue(make_milestone("Iteration-1", project_id=1), closed_at="2026-10-01T09:00:00.000Z"),
        make_issue(other_period),
        make_issue(other_prefix),
        make_issue(SPRINT),
    ]

    result = gbr([SPRINT, other_prefix], issues)

    assert result.stderr == ""


def test_only_first_five_unassigned_issues_are_linked() -> None:
    issues = [make_issue(None, project="colors/rainbow") for _ in range(7)]

    result = gbr([SPRINT], list(reversed(issues)))

    links = ", ".join(f"[colors/rainbow#{i['iid']}]({i['web_url']})" for i in issues[:5])
    assert warnings(result) == [
        f"期のスプリントにも Icebox にも割り当てられていない open の issue が 7 件あります: {links} ほか 2 件"
    ]


def test_unassigned_issues_are_ordered_by_project_then_iid() -> None:
    issues = [
        make_issue(None, project="colors/b"),
        make_issue(None, project="colors/a"),
    ]
    issues.append({**make_issue(None, project="colors/b"), "iid": 2})
    issues[-1]["references"] = {"full": "colors/b#2"}

    result = gbr([SPRINT], issues)

    [warning] = warnings(result)
    refs = [part.split("]")[0] for part in warning.split("[")[1:]]
    assert refs == [f"colors/a#{issues[1]['iid']}", "colors/b#2", f"colors/b#{issues[0]['iid']}"]
