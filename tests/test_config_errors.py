from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from gitlab_backlog_reporter.cli import RunResult, run
from tests.gitlab_fake import FakeGitLab, make_group, make_milestone

TODAY = date(2026, 10, 2)
TZ = ZoneInfo("Asia/Tokyo")
ENV = {"GITLAB_HOST": "http://gitlab.test", "GITLAB_PRIVATE_TOKEN": "secret"}


def unreachable(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"API を呼ぶべきではない: {request.url}")


def test_missing_env_vars_are_reported_together() -> None:
    result = run(["colors"], {}, TODAY, TZ, httpx.MockTransport(unreachable))

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == (
        "error: 環境変数 GITLAB_HOST が設定されていません。"
        "接続先の GitLab の URL を設定してください（例: GITLAB_HOST=https://gitlab.example.com）\n"
        "error: 環境変数 GITLAB_PRIVATE_TOKEN が設定されていません。"
        "read_api スコープを持つ personal access token を設定してください\n"
    )


def test_empty_env_var_is_treated_as_missing() -> None:
    env = {"GITLAB_HOST": "", "GITLAB_PRIVATE_TOKEN": "secret"}

    result = run(["colors"], env, TODAY, TZ, httpx.MockTransport(unreachable))

    assert result.exit_code == 1
    assert "GITLAB_HOST" in result.stderr
    assert "GITLAB_PRIVATE_TOKEN" not in result.stderr


def gbr(fake: FakeGitLab, *argv: str) -> RunResult:
    return run(list(argv) or ["colors"], ENV, TODAY, TZ, fake.transport())


def test_missing_group_argument_is_an_argument_error() -> None:
    result = run([], ENV, TODAY, TZ, httpx.MockTransport(unreachable))

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "group" in result.stderr


def test_help_is_printed_to_stdout() -> None:
    result = run(["--help"], ENV, TODAY, TZ, httpx.MockTransport(unreachable))

    assert result.exit_code == 0
    assert "--sprint-prefix" in result.stdout
    assert "--exclude-sprint-prefix" in result.stdout


def test_invalid_token() -> None:
    fake = FakeGitLab(make_group(), [], []).fail("group", 401)

    assert gbr(fake) == RunResult("", "error: token が無効か、期限切れです\n", 1)


def test_group_not_found() -> None:
    fake = FakeGitLab(make_group(), [], [])

    result = gbr(fake, "colours")

    assert result == RunResult(
        "", "error: group `colours` が見つからないか、token にアクセス権がありません\n", 1
    )


def test_no_sprint_matches_prefix_lists_group_milestones() -> None:
    milestones = [
        make_milestone("Iteration-Q3-2", "2026-10-15", "2026-10-28"),
        make_milestone("Icebox"),
        make_milestone("Iteration-Q3-1", "2026-10-01", "2026-10-14"),
    ]
    fake = FakeGitLab(make_group(), milestones, [])

    result = gbr(fake, "colors", "--sprint-prefix", "Iteration-Q4-")

    assert result == RunResult(
        "",
        'error: 名前が "Iteration-Q4-" で始まる group milestone がありません。'
        'group "colors" の milestone: Icebox, Iteration-Q3-1, Iteration-Q3-2\n',
        1,
    )


def test_all_sprints_excluded_names_the_excluded_milestones() -> None:
    milestones = [
        make_milestone("Iteration-3Q-2", "2026-10-15", "2026-10-28"),
        make_milestone("Icebox"),
        make_milestone("Iteration-3Q-1", "2026-10-01", "2026-10-14"),
    ]
    fake = FakeGitLab(make_group(), milestones, [])

    result = gbr(fake, "colors", "--exclude-sprint-prefix", "Iteration-3Q-")

    assert result == RunResult(
        "",
        'error: 名前が "Iteration-" で始まる group milestone は、すべて除外 prefix で除外されました: '
        "Iteration-3Q-1, Iteration-3Q-2\n",
        1,
    )


def test_no_group_milestones_at_all() -> None:
    fake = FakeGitLab(make_group(), [], [])

    result = gbr(fake)

    assert result.stderr == (
        'error: 名前が "Iteration-" で始まる group milestone がありません。group "colors" の milestone: （なし）\n'
    )


def test_sprints_with_missing_or_reversed_dates_are_all_named() -> None:
    milestones = [
        make_milestone("Iteration-Q3-1", "2026-10-01", "2026-10-14"),
        make_milestone("Iteration-Q3-2", None, "2026-10-28"),
        make_milestone("Iteration-Q3-3", "2026-10-29", None),
        make_milestone("Iteration-Q3-4", "2026-11-25", "2026-11-12"),
        make_milestone("Iteration-Q3-5", None, None),
        make_milestone("Icebox"),
    ]
    fake = FakeGitLab(make_group(), milestones, [])

    result = gbr(fake)

    assert result == RunResult(
        "",
        "error: 開始日か終了日がないスプリントがあります: Iteration-Q3-2, Iteration-Q3-3, Iteration-Q3-5\n"
        "error: 開始日が終了日より後のスプリントがあります: Iteration-Q3-4\n",
        1,
    )


def test_sprint_starting_and_ending_on_the_same_day_is_valid() -> None:
    fake = FakeGitLab(make_group(), [make_milestone("Iteration-1", "2026-10-01", "2026-10-01")], [])

    assert gbr(fake).exit_code == 0


def test_forbidden_shows_status_and_url_without_token() -> None:
    fake = FakeGitLab(make_group(), [], []).fail("group", 403)

    result = gbr(fake)

    assert result == RunResult(
        "",
        "error: GitLab API がエラーを返しました（HTTP 403）: "
        "GET http://gitlab.test/api/v4/groups/colors?with_projects=false\n",
        1,
    )


def test_server_error_on_paged_endpoint_shows_status_and_url() -> None:
    fake = FakeGitLab(make_group(), [], []).fail("issues", 502)

    result = gbr(fake)

    assert result == RunResult(
        "",
        "error: GitLab API がエラーを返しました（HTTP 502）: "
        "GET http://gitlab.test/api/v4/groups/10/issues?include_subgroups=true&state=all&scope=all&per_page=100&page=1\n",
        1,
    )


def test_not_found_on_milestones_is_not_reported_as_missing_group() -> None:
    fake = FakeGitLab(make_group(), [], []).fail("milestones", 404)

    result = gbr(fake)

    assert result.exit_code == 1
    assert result.stderr == (
        "error: GitLab API がエラーを返しました（HTTP 404）: "
        "GET http://gitlab.test/api/v4/groups/10/milestones?per_page=100&page=1\n"
    )


def test_connection_failure_shows_url_without_token() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("[Errno 111] Connection refused", request=request)

    result = run(["colors"], ENV, TODAY, TZ, httpx.MockTransport(refuse))

    assert result == RunResult(
        "",
        "error: GitLab API に接続できませんでした（[Errno 111] Connection refused）: "
        "GET http://gitlab.test/api/v4/groups/colors?with_projects=false\n",
        1,
    )
    assert "secret" not in result.stderr


def test_api_errors_are_not_retried() -> None:
    fake = FakeGitLab(make_group(), [], []).fail("group", 503)

    gbr(fake)

    assert len(fake.requests) == 1


SPRINTS = [make_milestone("Iteration-1", "2026-10-01", "2026-10-14"), make_milestone("Icebox")]


def test_unparsable_holidays_are_all_named_with_line_numbers(tmp_path: Path) -> None:
    holidays = tmp_path / "holidays.txt"
    holidays.write_text("# 2026 年\n2026-01-01\n2026/01/12  # 成人の日\n2026-02-30\n20260223\n", encoding="utf-8")

    result = run(["colors", "--holidays", str(holidays)], ENV, TODAY, TZ, httpx.MockTransport(unreachable))

    assert result == RunResult(
        "",
        f"error: 休業日のファイル {holidays} の 3 行目を日付として解釈できません（YYYY-MM-DD で書いてください）: 2026/01/12\n"
        f"error: 休業日のファイル {holidays} の 4 行目を日付として解釈できません（YYYY-MM-DD で書いてください）: 2026-02-30\n"
        f"error: 休業日のファイル {holidays} の 5 行目を日付として解釈できません（YYYY-MM-DD で書いてください）: 20260223\n",
        1,
    )


def test_missing_holidays_file(tmp_path: Path) -> None:
    holidays = tmp_path / "missing.txt"

    result = run(["colors", "--holidays", str(holidays)], ENV, TODAY, TZ, httpx.MockTransport(unreachable))

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.startswith(f"error: 休業日のファイル {holidays} を読めません（")


def test_valid_holidays_file_does_not_fail(tmp_path: Path) -> None:
    holidays = tmp_path / "holidays.txt"
    holidays.write_text("2026-01-01  # 元日\n", encoding="utf-8")
    fake = FakeGitLab(make_group(), SPRINTS, [])

    assert gbr(fake, "colors", "--holidays", str(holidays)).exit_code == 0
