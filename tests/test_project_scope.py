"""project を集計範囲にしたレポート（`--project`）。スプリントと Icebox は project milestone からだけ選ぶ。"""

from datetime import date
from zoneinfo import ZoneInfo

from gitlab_backlog_reporter.cli import RunResult, run
from tests.gitlab_fake import FakeGitLab, Json, make_issue, make_milestone, make_project

TODAY = date(2026, 10, 2)
TZ = ZoneInfo("Asia/Tokyo")
ENV = {"GITLAB_HOST": "http://gitlab.test", "GITLAB_PRIVATE_TOKEN": "secret"}


def project_milestone(title: str, start_date: str | None = None, due_date: str | None = None) -> Json:
    return make_milestone(title, start_date, due_date, project_id=20)


def gbr(fake: FakeGitLab, *args: str) -> RunResult:
    return run(["--project", *(args or ("colors/red",))], ENV, TODAY, TZ, fake.transport())


def test_project_milestones_are_sprints_and_icebox() -> None:
    q1 = project_milestone("Iteration-Q3-1", "2026-10-01", "2026-10-14")
    q2 = project_milestone("Iteration-Q3-2", "2026-10-15", "2026-10-28")
    icebox = project_milestone("Icebox")
    fake = FakeGitLab(
        make_project(),
        [q1, q2, icebox],
        [
            make_issue(q1, project="colors/red", closed_at="2026-10-01T09:00:00.000Z"),
            make_issue(q2, project="colors/red"),
            make_issue(icebox, project="colors/red"),
        ],
    )

    result = gbr(fake)

    assert (result.stderr, result.exit_code) == ("", 0)
    assert result.stdout.startswith(
        "# バックログレポート: colors/red / Iteration-\n"
        "\n"
        "| 接続先 | 集計範囲 | 期 | 基準日 |\n"
        "|---|---|---|---|\n"
        "| http://gitlab.test | `colors/red`（project） | `Iteration-`（10/1〜10/28、2 スプリント） | 2026-10-02 |\n"
    )
    assert "| 対象バックログ | 2 |" in result.stdout
    assert "| 消化 | 1 |" in result.stdout
    assert "| Icebox（open、参考） | 1 |" in result.stdout


def test_project_endpoints_are_requested_without_ancestor_milestones() -> None:
    fake = FakeGitLab(make_project(), [project_milestone("Iteration-1", "2026-10-01", "2026-10-14")], [])

    gbr(fake)

    assert [(r.url.path, dict(r.url.params)) for r in fake.requests] == [
        ("/api/v4/projects/colors/red", {}),
        ("/api/v4/projects/20/milestones", {"per_page": "100", "page": "1"}),
        ("/api/v4/projects/20/issues", {"state": "all", "per_page": "100", "page": "1"}),
    ]
    assert fake.requests[0].url.raw_path == b"/api/v4/projects/colors%2Fred"


def test_numeric_project_is_an_id_and_header_shows_full_path() -> None:
    fake = FakeGitLab(make_project(id=42), [project_milestone("Iteration-1", "2026-10-01", "2026-10-14")], [])

    result = gbr(fake, "42")

    assert fake.requests[0].url.raw_path == b"/api/v4/projects/42"
    assert "| `colors/red`（project） |" in result.stdout
    assert result.stdout.startswith("# バックログレポート: colors/red / Iteration-\n")


def test_group_milestones_are_neither_sprints_nor_icebox_and_their_open_issues_are_warned() -> None:
    sprint = project_milestone("Iteration-1", "2026-10-01", "2026-10-14")
    group_sprint = make_milestone("Iteration-2", "2026-10-15", "2026-10-28", group_id=10)
    group_icebox = make_milestone("Icebox", group_id=10)
    in_group_sprint = make_issue(group_sprint, project="colors/red")
    in_group_icebox = make_issue(group_icebox, project="colors/red")
    without_milestone = make_issue(None, project="colors/red")
    issues = [
        make_issue(sprint, project="colors/red"),
        in_group_sprint,
        in_group_icebox,
        without_milestone,
        make_issue(group_sprint, project="colors/red", closed_at="2026-10-01T09:00:00.000Z"),
    ]
    # project の milestones は祖先の group milestone を含まないので、issue からしか見えない
    fake = FakeGitLab(make_project(), [sprint], issues)

    result = gbr(fake)

    a, b, c = in_group_sprint, in_group_icebox, without_milestone
    assert result == RunResult(
        result.stdout,
        'warning: Icebox の project milestone "Icebox" が見つかりません\n'
        "warning: 期のスプリントにも Icebox にも割り当てられていない open の issue が 3 件あります: "
        f"[colors/red#{a['iid']}]({a['web_url']}), "
        f"[colors/red#{b['iid']}]({b['web_url']}), "
        f"[colors/red#{c['iid']}]({c['web_url']})\n",
        0,
    )
    assert "`Iteration-`（10/1〜10/14、1 スプリント）" in result.stdout


def test_other_project_milestones_are_not_warned() -> None:
    sprint = project_milestone("Iteration-1", "2026-10-01", "2026-10-14")
    release = project_milestone("Release-1")
    fake = FakeGitLab(
        make_project(),
        [sprint, release, project_milestone("Icebox")],
        [make_issue(sprint, project="colors/red"), make_issue(release, project="colors/red")],
    )

    assert gbr(fake).stderr == ""


def test_project_not_found() -> None:
    fake = FakeGitLab(make_project(), [], [])

    result = gbr(fake, "colors/blue")

    assert result == RunResult("", "error: project `colors/blue` が見つからないか、token にアクセス権がありません\n", 1)


def test_group_path_given_with_project_flag_is_not_found_as_project() -> None:
    fake = FakeGitLab(make_project(), [], [])

    result = gbr(fake, "colors")

    assert result == RunResult("", "error: project `colors` が見つからないか、token にアクセス権がありません\n", 1)


def test_no_sprint_matches_prefix_lists_project_milestones() -> None:
    fake = FakeGitLab(make_project(), [project_milestone("Icebox"), project_milestone("Release-1")], [])

    result = gbr(fake)

    assert result == RunResult(
        "",
        'error: 名前が "Iteration-" で始まる project milestone がありません。'
        'project "colors/red" の milestone: Icebox, Release-1\n',
        1,
    )


def test_all_sprints_excluded_is_reported_with_project_milestones() -> None:
    fake = FakeGitLab(make_project(), [project_milestone("Iteration-3Q-1", "2026-10-01", "2026-10-14")], [])

    result = gbr(fake, "colors/red", "--exclude-sprint-prefix", "Iteration-3Q-")

    assert result == RunResult(
        "",
        'error: 名前が "Iteration-" で始まる project milestone は、すべて除外 prefix で除外されました: Iteration-3Q-1\n',
        1,
    )


def test_exclude_prefix_that_excludes_nothing_names_project_milestones() -> None:
    sprint = project_milestone("Iteration-1", "2026-10-01", "2026-10-14")
    fake = FakeGitLab(make_project(), [sprint, project_milestone("Icebox")], [make_issue(sprint, project="colors/red")])

    result = gbr(fake, "colors/red", "--exclude-sprint-prefix", "Release-")

    assert result.stderr == (
        'warning: 除外 prefix "Release-" は何も除外していません（名前が "Iteration-" で始まる project milestone に該当なし）\n'
    )


def test_icebox_option_selects_project_milestone() -> None:
    sprint = project_milestone("Iteration-1", "2026-10-01", "2026-10-14")
    freezer = project_milestone("Freezer")
    fake = FakeGitLab(
        make_project(),
        [sprint, freezer],
        [make_issue(sprint, project="colors/red"), make_issue(freezer, project="colors/red")],
    )

    result = gbr(fake, "colors/red", "--icebox", "Freezer")

    assert result.stderr == ""
    assert "| Icebox（open、参考） | 1 |" in result.stdout
