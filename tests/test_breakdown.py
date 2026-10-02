from tests.gitlab_fake import FakeGitLab, make_group, make_issue, make_milestone
from tests.test_report import gbr, sprints

CLOSED = "2026-10-01T09:00:00.000Z"


def test_label_breakdown_counts_each_label_except_status() -> None:
    q1, q2 = sprints()
    icebox = make_milestone("Icebox")
    fake = FakeGitLab(
        make_group(),
        [q1, q2, icebox],
        [
            make_issue(q1, closed_at=CLOSED, labels=["type::feature", "frontend"]),
            make_issue(q1, labels=["type::feature", "backend", "status::doing"]),
            make_issue(q2, closed_at=CLOSED, labels=["backend"]),
            make_issue(q2, labels=["status::ready"]),
            make_issue(q2),
            make_issue(icebox, labels=["icebox-only"]),
        ],
    )

    result = gbr(fake)

    assert (
        "## 内訳\n"
        "\n"
        "### ラベル別\n"
        "\n"
        "| ラベル | 件数 | 消化 | 進捗率 |\n"
        "|---|---:|---:|---:|\n"
        "| `backend` | 2 | 1 | 50% |\n"
        "| `frontend` | 1 | 1 | 100% |\n"
        "| `type::feature` | 2 | 1 | 50% |\n"
        "| （なし） | 2 | 0 | 0% |\n"
    ) in result.stdout


def test_assignee_breakdown_counts_each_assignee_and_notes_it() -> None:
    q1, q2 = sprints()
    fake = FakeGitLab(
        make_group(),
        [q1, q2, make_milestone("Icebox")],
        [
            make_issue(q1, closed_at=CLOSED, assignees=["bob"]),
            make_issue(q1, closed_at=CLOSED, assignees=["alice", "bob"]),
            make_issue(q2, assignees=["alice"]),
            make_issue(q2),
        ],
    )

    result = gbr(fake)

    assert (
        "### 担当者別\n"
        "\n"
        "| 担当者 | 件数 | 消化 | 残り |\n"
        "|---|---:|---:|---:|\n"
        "| @alice | 2 | 1 | 1 |\n"
        "| @bob | 2 | 2 | 0 |\n"
        "| （なし） | 1 | 0 | 1 |\n"
        "\n"
        "※ 担当者が複数いるバックログは、それぞれの担当者に数えています。\n"
    ) in result.stdout


def test_none_row_is_omitted_when_every_backlog_has_one() -> None:
    q1, _ = sprints()
    fake = FakeGitLab(
        make_group(), [q1, make_milestone("Icebox")], [make_issue(q1, labels=["backend"], assignees=["alice"])]
    )

    result = gbr(fake)

    assert "| （なし） |" not in result.stdout


def test_breakdown_without_target_backlog_shows_dash() -> None:
    fake = FakeGitLab(make_group(), [*sprints(), make_milestone("Icebox")], [])

    result = gbr(fake)

    assert "| ラベル | 件数 | 消化 | 進捗率 |\n|---|---:|---:|---:|\n| （なし） | 0 | 0 | — |\n" in result.stdout
    assert "| 担当者 | 件数 | 消化 | 残り |\n|---|---:|---:|---:|\n| （なし） | 0 | 0 | 0 |\n" in result.stdout


def test_breakdown_follows_summary() -> None:
    fake = FakeGitLab(make_group(), [*sprints(), make_milestone("Icebox")], [])

    result = gbr(fake)

    assert result.stdout.index("## サマリー") < result.stdout.index("## 内訳")
