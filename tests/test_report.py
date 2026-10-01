from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from gitlab_backlog_reporter.cli import RunResult, run
from tests.gitlab_fake import FakeGitLab, Json, make_group, make_issue, make_milestone

TODAY = date(2026, 10, 2)
TZ = ZoneInfo("Asia/Tokyo")
ENV = {"GITLAB_HOST": "http://gitlab.test", "GITLAB_PRIVATE_TOKEN": "secret"}


def sprints() -> list[Json]:
    return [
        make_milestone("Iteration-Q3-1", "2026-10-01", "2026-10-14"),
        make_milestone("Iteration-Q3-2", "2026-10-15", "2026-10-28", state="closed"),
    ]


def gbr(fake: FakeGitLab, *args: str, env: dict[str, str] = ENV) -> RunResult:
    return run(["colors", *args], env, TODAY, TZ, fake.transport())


def test_header_and_summary_count_issues_in_the_periods_sprints() -> None:
    q1, q2 = sprints()
    icebox = make_milestone("Icebox")
    other_period = make_milestone("Iteration-Q2-6", "2026-09-17", "2026-09-30")
    project_sprint = make_milestone("Iteration-Q3-1", "2026-10-01", "2026-10-14", project_id=1)
    in_project_sprint = make_issue(project_sprint)
    without_milestone = make_issue(None)
    fake = FakeGitLab(
        make_group(),
        [q1, q2, icebox, other_period],
        [
            make_issue(q1, closed_at="2026-10-01T09:00:00.000Z"),
            make_issue(q1),
            make_issue(q2),
            make_issue(q2),
            make_issue(icebox),
            make_issue(icebox),
            make_issue(icebox, closed_at="2026-09-01T09:00:00.000Z"),
            make_issue(other_period),
            in_project_sprint,
            without_milestone,
        ],
    )

    result = gbr(fake, "--sprint-prefix", "Iteration-Q3-")

    unassigned = (
        "期のスプリントにも Icebox にも割り当てられていない open の issue が 2 件あります: "
        f"[colors/rainbow#{in_project_sprint['iid']}]({in_project_sprint['web_url']}), "
        f"[colors/rainbow#{without_milestone['iid']}]({without_milestone['web_url']})"
    )
    assert result.stderr == f"warning: {unassigned}\n"
    assert result.exit_code == 0
    assert result.stdout == (
        "# バックログレポート: colors / Iteration-Q3-\n"
        "\n"
        "| 接続先 | group | 期 | 基準日 |\n"
        "|---|---|---|---|\n"
        "| http://gitlab.test | `colors` | `Iteration-Q3-`（10/1〜10/28、2 スプリント） | 2026-10-02 |\n"
        "\n"
        "> [!WARNING]\n"
        f"> - {unassigned}\n"
        "\n"
        "## サマリー\n"
        "\n"
        "**進捗率 25%** `█████░░░░░░░░░░░░░░░` 1 / 4 件\n"
        "\n"
        "| 指標 | 件数 |\n"
        "|---|---:|\n"
        "| 対象バックログ | 4 |\n"
        "| 消化 | 1 |\n"
        "| 残り（今日） | **3** |\n"
        "| Icebox（open、参考） | 2 |\n"
    )


def test_all_pages_of_milestones_and_issues_are_read() -> None:
    q1, q2 = sprints()
    issues = [make_issue(q1, closed_at="2026-10-01T09:00:00.000Z") for _ in range(3)]
    issues += [make_issue(q2) for _ in range(4)]
    fake = FakeGitLab(make_group(), [make_milestone(f"Other-{n}") for n in range(5)] + [q1, q2], issues, per_page=2)

    result = gbr(fake, "--icebox", "Other-0")

    assert result.exit_code == 0
    assert "**進捗率 43%** `█████████░░░░░░░░░░░` 3 / 7 件" in result.stdout
    assert "`Iteration-`（10/1〜10/28、2 スプリント）" in result.stdout


def test_issues_are_requested_across_subgroups() -> None:
    fake = FakeGitLab(make_group(), [*sprints(), make_milestone("Icebox")], [])

    gbr(fake)

    issue_requests = [r for r in fake.requests if r.url.path.endswith("/issues")]
    assert issue_requests[0].url.params["include_subgroups"] == "true"


def test_sprint_prefix_and_icebox_are_case_sensitive() -> None:
    q1, q2 = sprints()
    lower_sprint = make_milestone("iteration-Q3-9", "2026-10-29", "2026-11-11")
    lower_icebox = make_milestone("icebox")
    fake = FakeGitLab(make_group(), [q1, q2, lower_sprint, lower_icebox], [make_issue(lower_sprint)])

    result = gbr(fake)

    assert "2 スプリント" in result.stdout
    assert "| 対象バックログ | 0 |" in result.stdout
    assert 'warning: Icebox の group milestone "Icebox" が見つかりません' in result.stderr


def test_missing_icebox_is_a_warning_in_report_and_stderr() -> None:
    fake = FakeGitLab(make_group(), sprints(), [])

    result = gbr(fake)

    assert result.exit_code == 0
    assert result.stderr == 'warning: Icebox の group milestone "Icebox" が見つかりません\n'
    assert (
        "| 2026-10-02 |\n"
        "\n"
        "> [!WARNING]\n"
        '> - Icebox の group milestone "Icebox" が見つかりません\n'
        "\n"
        "## サマリー\n"
    ) in result.stdout
    assert "| Icebox（open、参考） | — |" in result.stdout


def test_custom_icebox_name_is_matched_exactly() -> None:
    q1, q2 = sprints()
    old_freezer = make_milestone("Freezer-old")
    freezer = make_milestone("Freezer")
    fake = FakeGitLab(
        make_group(),
        [q1, q2, old_freezer, freezer],
        [make_issue(freezer), make_issue(old_freezer), make_issue(old_freezer)],
    )

    result = gbr(fake, "--icebox", "Freezer")

    assert result.stderr == ""
    assert "| Icebox（open、参考） | 1 |" in result.stdout


def test_no_target_backlog_shows_dash_without_bar() -> None:
    fake = FakeGitLab(make_group(), [*sprints(), make_milestone("Icebox")], [])

    result = gbr(fake)

    assert result.exit_code == 0
    assert "**進捗率 —** 0 / 0 件\n" in result.stdout
    assert "█" not in result.stdout and "░" not in result.stdout


def test_full_progress_fills_the_bar() -> None:
    q1, _ = sprints()
    fake = FakeGitLab(
        make_group(), [q1, make_milestone("Icebox")], [make_issue(q1, closed_at="2026-10-01T09:00:00.000Z")]
    )

    result = gbr(fake)

    assert "**進捗率 100%** `████████████████████` 1 / 1 件" in result.stdout
    assert "| 残り（今日） | **0** |" in result.stdout


def test_period_spans_first_start_to_last_end_regardless_of_order() -> None:
    milestones = [
        make_milestone("Iteration-Q3-3", "2026-10-29", "2026-11-11"),
        make_milestone("Iteration-Q3-1", "2026-10-01", "2026-10-14"),
        make_milestone("Icebox"),
    ]
    fake = FakeGitLab(make_group(), milestones, [])

    result = gbr(fake)

    assert "`Iteration-`（10/1〜11/11、2 スプリント）" in result.stdout


def test_output_option_writes_report_to_file(tmp_path: Path) -> None:
    output = tmp_path / "report.md"
    output.write_text("前回のレポート")
    fake = FakeGitLab(make_group(), [*sprints(), make_milestone("Icebox")], [])

    result = gbr(fake, "-o", str(output))

    assert result == RunResult("", "", 0)
    assert output.read_text(encoding="utf-8").startswith("# バックログレポート: colors / Iteration-\n")


def test_error_leaves_existing_output_file_untouched(tmp_path: Path) -> None:
    output = tmp_path / "report.md"
    output.write_text("前回のレポート")
    fake = FakeGitLab(make_group(), [make_milestone("Icebox")], [])

    result = gbr(fake, "--output", str(output))

    assert result.exit_code == 1
    assert output.read_text() == "前回のレポート"


def test_host_without_scheme_gets_https() -> None:
    fake = FakeGitLab(make_group(), [*sprints(), make_milestone("Icebox")], [])

    result = gbr(fake, env={**ENV, "GITLAB_HOST": "gitlab.test/"})

    assert all(str(r.url).startswith("https://gitlab.test/api/v4/") for r in fake.requests)
    assert "| https://gitlab.test | `colors` |" in result.stdout


def test_token_is_sent_as_private_token_header() -> None:
    fake = FakeGitLab(make_group(), [*sprints(), make_milestone("Icebox")], [])

    gbr(fake)

    assert {r.headers["PRIVATE-TOKEN"] for r in fake.requests} == {"secret"}


def test_numeric_group_is_an_id_and_header_shows_full_path() -> None:
    fake = FakeGitLab(make_group("colors/team", id=42), [*sprints(), make_milestone("Icebox")], [])

    result = run(["42"], ENV, TODAY, TZ, fake.transport())

    assert fake.requests[0].url.raw_path.split(b"?")[0] == b"/api/v4/groups/42"
    assert result.stdout.startswith("# バックログレポート: colors/team / Iteration-\n")
    assert "| `colors/team` |" in result.stdout


def test_subgroup_full_path_is_url_encoded() -> None:
    fake = FakeGitLab(make_group("colors/team", id=42), [*sprints(), make_milestone("Icebox")], [])

    result = run(["colors/team"], ENV, TODAY, TZ, fake.transport())

    assert result.exit_code == 0
    assert fake.requests[0].url.raw_path.split(b"?")[0] == b"/api/v4/groups/colors%2Fteam"
