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


def gbr(fake: FakeGitLab, *args: str, env: dict[str, str] = ENV, today: date = TODAY) -> RunResult:
    return run(["colors", *args], env, today, TZ, fake.transport())


def test_header_and_summary_count_issues_in_the_periods_sprints() -> None:
    q1, q2 = sprints()
    icebox = make_milestone("Icebox")
    other_period = make_milestone("Iteration-Q2-6", "2026-09-17", "2026-09-30")
    project_sprint = make_milestone("Iteration-Q3-1", "2026-10-01", "2026-10-14", project_id=1)
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
            make_issue(project_sprint),
            make_issue(None),
        ],
    )

    result = gbr(fake, "--sprint-prefix", "Iteration-Q3-")

    assert result.stderr == ""
    assert result.exit_code == 0
    assert result.stdout.startswith(
        "# バックログレポート: colors / Iteration-Q3-\n"
        "\n"
        "| 接続先 | group | 期 | 基準日 |\n"
        "|---|---|---|---|\n"
        "| http://gitlab.test | `colors` | `Iteration-Q3-`（10/1〜10/28、2 スプリント） | 2026-10-02 |\n"
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
        "| 予定線の今日の値 | 3.9 |\n"
        "| 理想線の今日の値 | 3.9 |\n"
        "| Icebox（open、参考） | 2 |\n"
        "\n"
        "## バーンダウン\n"
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
    q1, q2 = sprints()
    fake = FakeGitLab(make_group(), [q1, q2], [make_issue(q1)])

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
        [make_issue(q1), make_issue(freezer), make_issue(old_freezer), make_issue(old_freezer)],
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
    q1, q2 = sprints()
    fake = FakeGitLab(make_group(), [q1, q2, make_milestone("Icebox")], [make_issue(q1)])

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


NOTE = (
    "※ 3本の線は、すべて実行時点の割り当てから計算しています。"
    "スプリント間で移したバックログや、途中で追加したバックログは、過去の点にもさかのぼって反映されます"
    "（理想線の始点と予定線の段差は、当時の計画とは異なる場合があります）。"
)


def burndown_fake() -> FakeGitLab:
    """Iteration-Q3-1 に3件（1件は 10/1 に消化）、Iteration-Q3-2 に1件。"""
    q1, q2 = sprints()
    return FakeGitLab(
        make_group(),
        [q1, q2, make_milestone("Icebox")],
        [
            make_issue(q1, closed_at="2026-10-01T09:00:00.000Z"),
            make_issue(q1),
            make_issue(q1),
            make_issue(q2),
        ],
    )


def burndown_section(stdout: str) -> str:
    return stdout.split("## バーンダウン\n\n", 1)[1]


def test_burndown_draws_three_lines_with_actual_up_to_today() -> None:
    result = gbr(burndown_fake(), "--sprint-prefix", "Iteration-Q3-", today=date(2026, 10, 16))

    assert result.stderr == ""
    assert burndown_section(result.stdout) == (
        "```mermaid\n"
        "---\n"
        "config:\n"
        "  xyChart:\n"
        "    xAxis:\n"
        "      labelRotation: -45\n"
        "  themeVariables:\n"
        "    xyChart:\n"
        '      plotColorPalette: "#9e9e9e, #1f77b4, #d62728"\n'
        "---\n"
        "xychart-beta\n"
        '  title "Iteration-Q3- バーンダウン"\n'
        '  x-axis "週" ["10/1", "10/8", "10/15", "10/22", "10/29"]\n'
        '  y-axis "残件数" 0 --> 4\n'
        '  line "理想" [4, 3, 2, 1, 0]\n'
        '  line "予定" [4, 2.5, 1, 0.5, 0]\n'
        '  line "実績" [4, 3, 3]\n'
        "```\n"
        "\n"
        "凡例: 灰 = 理想 / 青 = 予定 / 赤 = 実績\n"
        "\n"
        f"{NOTE}\n"
    )


def test_summary_shows_todays_planned_and_ideal_values() -> None:
    result = gbr(burndown_fake(), today=date(2026, 10, 16))

    assert (
        "| 残り（今日） | **3** |\n"
        "| 予定線の今日の値 | 0.9 |\n"
        "| 理想線の今日の値 | 1.9 |\n"
        "| Icebox（open、参考） | 0 |\n"
    ) in result.stdout


def test_closed_at_is_dated_in_the_local_time_zone() -> None:
    q1, q2 = sprints()
    fake = FakeGitLab(
        make_group(),
        [q1, q2, make_milestone("Icebox")],
        [
            # 10/7 23:59 JST
            make_issue(q1, closed_at="2026-10-07T14:59:00.000Z"),
            # 10/8 00:00 JST
            make_issue(q1, closed_at="2026-10-07T15:00:00.000Z"),
            make_issue(q2),
        ],
    )

    result = gbr(fake, today=date(2026, 10, 15))

    assert '  line "実績" [3, 2, 1]\n' in result.stdout


def test_before_the_period_there_is_no_actual_line() -> None:
    result = gbr(burndown_fake(), today=date(2026, 9, 30))

    section = burndown_section(result.stdout)
    assert result.stderr == ""
    assert '  line "予定" [4, 2.5, 1, 0.5, 0]\n```\n' in section
    assert "実績\" [" not in section
    assert section.endswith(
        "凡例: 灰 = 理想 / 青 = 予定 / 赤 = 実績\n\n期が始まる前のため、実績線はありません\n\n" f"{NOTE}\n"
    )
    assert "| 予定線の今日の値 | 4 |\n| 理想線の今日の値 | 4 |\n" in result.stdout


def test_on_the_first_day_actual_line_has_one_point() -> None:
    result = gbr(burndown_fake(), today=date(2026, 10, 1))

    assert '  line "実績" [4]\n' in result.stdout
    assert "実績線はありません" not in result.stdout


def test_after_the_period_actual_line_is_drawn_at_every_point() -> None:
    result = gbr(burndown_fake(), today=date(2026, 11, 30))

    assert result.stderr == ""
    assert '  line "実績" [4, 3, 3, 3, 3]\n' in result.stdout
    assert "| 予定線の今日の値 | 0 |\n| 理想線の今日の値 | 0 |\n" in result.stdout


def test_on_the_day_after_the_period_actual_line_reaches_the_last_point() -> None:
    result = gbr(burndown_fake(), today=date(2026, 10, 29))

    assert '  line "実績" [4, 3, 3, 3, 3]\n' in result.stdout


def test_no_target_backlog_replaces_the_chart_with_a_sentence_and_warns() -> None:
    fake = FakeGitLab(make_group(), [*sprints(), make_milestone("Icebox")], [])

    result = gbr(fake)

    assert result.exit_code == 0
    assert result.stderr == "warning: 対象バックログが 0件です\n"
    assert "> [!WARNING]\n> - 対象バックログが 0件です\n" in result.stdout
    assert burndown_section(result.stdout) == "対象バックログがないため、バーンダウンは表示しません\n"
    assert "```mermaid" not in result.stdout
    assert "| 予定線の今日の値 | 0 |\n| 理想線の今日の値 | 0 |\n" in result.stdout
