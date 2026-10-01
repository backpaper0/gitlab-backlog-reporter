from datetime import date
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
