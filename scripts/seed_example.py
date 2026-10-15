"""example/compose.yaml で立てた GitLab に、サンプルデータ（group colors）を投入する。

使い方: docker compose -f example/compose.yaml up -d --wait のあとで uv run scripts/seed_example.py

root の personal access token（api、sudo）を gitlab-rails runner で発行して example/.token に保存し、それを使って
REST API でユーザー、group、project、ラベル、スプリント、バックログを作る。バックログは Sudo で各ユーザーとして作る。
REST API では過去の日時にできない created_at と closed_at、CE では API から複数にできない担当者は、最後に
gitlab-rails runner で書き換える。

group colors がすでにあれば、何も変えずにエラーで止まる。立て直すときは docker compose down -v からやり直す。
"""

import base64
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from gitlab_backlog_reporter.gitlab import Json

HOST = "http://localhost:9080"
EXAMPLE = Path(__file__).resolve().parent.parent / "example"
TOKEN_FILE = EXAMPLE / ".token"
TZ = ZoneInfo("Asia/Tokyo")

GROUP = "colors"
USERS = ["kuro", "shiro", "aka", "ao", "midori"]
LABELS = {
    "status::ready": "#428bca",
    "status::doing": "#f0ad4e",
    "status::review": "#8e44ad",
    "type::feature": "#5cb85c",
    "type::bug": "#d9534f",
    "frontend": "#00b140",
    "backend": "#6699cc",
}
SPRINT_COUNT = 6
FIRST_SPRINT_START = date(2026, 8, 6)
SPRINT_DAYS = 14
ICEBOX = "Icebox"
DEVELOPER = 30


def sprint_title(number: int) -> str:
    return f"Iteration-{number}"


@dataclass(frozen=True)
class Backlog:
    project: str
    title: str
    state: str
    """バックログ状態（open / ready / doing / review / close）。"""
    labels: tuple[str, ...] = ()
    """status:: 以外のラベル。"""
    assignees: tuple[str, ...] = ()
    closed_on: date | None = None


def backlog(
    project: str,
    title: str,
    state: str,
    labels: tuple[str, ...] = (),
    assignees: tuple[str, ...] = (),
    closed_on: str | None = None,
) -> Backlog:
    return Backlog(
        project, title, state, labels, assignees, date.fromisoformat(f"2026-{closed_on}") if closed_on else None
    )


FEATURE, BUG, FRONT, BACK = "type::feature", "type::bug", "frontend", "backend"

# スプリント（1 始まり）ごとのバックログ。1〜4 は終わったスプリント、5 は進行中（今日 10/7）、6 は未来。
SPRINTS: list[list[Backlog]] = [
    [
        backlog("hello", "ユーザー登録画面を作成する", "close", (FEATURE, FRONT), ("aka",), "08-10"),
        backlog("hello", "ログイン画面を作成する", "close", (FEATURE, FRONT), ("aka", "ao"), "08-12"),
        backlog("hello", "パスワードのハッシュ化を実装する", "close", (BACK,), ("kuro",), "08-11"),
        backlog("hello", "DB スキーマ（users, tasks）を設計する", "close", (BACK,), ("kuro", "shiro"), "08-07"),
        backlog("hello", "CI パイプラインを構築する", "close", (), ("midori",), "08-14"),
        backlog("world", "ステージング環境を構築する", "close", (), ("midori",), "08-18"),
        backlog("world", "ログ収集基盤を整備する", "open", (BACK,)),
    ],
    [
        backlog("hello", "タスク一覧 API を実装する", "close", (FEATURE, BACK), ("shiro",), "08-21"),
        backlog("hello", "タスク一覧画面を作成する", "close", (FEATURE, FRONT), ("ao",), "08-25"),
        backlog("hello", "タスク作成 API を実装する", "close", (FEATURE, BACK), ("shiro",), "08-26"),
        backlog("hello", "タスク作成フォームを作成する", "close", (FRONT,), ("ao", "aka"), "08-28"),
        backlog("hello", "ログアウト機能を実装する", "close", (FEATURE,), (), "08-31"),
        backlog("world", "監視ダッシュボードを構築する", "close", (), ("midori",), "09-01"),
        backlog("world", "管理者向けユーザー一覧画面を作成する", "doing", (FEATURE, FRONT), ("aka",)),
    ],
    [
        backlog("hello", "タスク編集機能を実装する", "close", (FEATURE,), ("shiro", "ao"), "09-04"),
        backlog("hello", "タスク削除機能を実装する", "close", (FEATURE, BACK), ("shiro",), "09-08"),
        backlog("hello", "タスクの完了／未完了を切り替えられるようにする", "close", (FRONT,), ("ao",), "09-09"),
        backlog("hello", "タスクに期限日を設定できるようにする", "close", (FEATURE,), ("kuro",), "09-11"),
        backlog("hello", "パスワードリセット機能を実装する", "open", (FEATURE, BACK)),
        backlog("world", "管理者向けユーザー停止機能を実装する", "close", (FEATURE, BACK), ("kuro",), "09-14"),
        backlog("world", "API ドキュメントを公開する", "close", (), (), "09-15"),
    ],
    [
        backlog("hello", "タスク一覧を期限日でソートできるようにする", "close", (FEATURE, BACK), ("shiro",), "09-18"),
        backlog("hello", "タスクのキーワード検索を実装する", "close", (FEATURE, BACK), ("kuro",), "09-22"),
        backlog("hello", "タスクにタグを付けられるようにする", "close", (FEATURE,), ("aka", "shiro"), "09-24"),
        backlog("hello", "タグでタスクを絞り込めるようにする", "close", (FRONT,), ("aka",), "09-25"),
        backlog("hello", "タスクの優先度を設定できるようにする", "review", (FEATURE,), ("ao",)),
        backlog("world", "エラー通知を Slack に送る", "close", (BACK,), ("midori",), "09-29"),
        backlog("world", "管理画面でユーザー名が文字化けする不具合を直す", "close", (BUG, FRONT), ("aka",), "09-30"),
    ],
    [
        backlog("hello", "ページネーションを実装する", "close", (BACK,), ("shiro",), "10-02"),
        backlog("hello", "期限前日にメール通知を送る", "review", (FEATURE, BACK), ("kuro", "midori")),
        backlog("hello", "プロフィール編集画面を作成する", "review", (FRONT,), ("aka",)),
        backlog("hello", "レスポンシブデザインに対応する", "doing", (FRONT,), ("ao",)),
        backlog("hello", "E2E テストを整備する", "ready", (), ("midori",)),
        backlog("world", "監査ログを記録する", "close", (FEATURE, BACK), ("kuro",), "10-05"),
        backlog("world", "権限管理（ロール）を実装する", "doing", (FEATURE, BACK), ("shiro", "kuro")),
        backlog("world", "負荷試験を実施する", "ready"),
    ],
    [
        backlog("hello", "タスクをチームメンバーに共有できるようにする", "ready", (FEATURE,), ("aka",)),
        backlog("hello", "タスクにコメントを付けられるようにする", "ready", (FEATURE, FRONT)),
        backlog("hello", "操作履歴（アクティビティログ）を表示する", "ready", (FRONT,)),
        backlog("hello", "本番環境へのデプロイ手順を整備する", "ready", (), ("midori",)),
        backlog("world", "バックアップを自動化する", "ready", (BACK,)),
        backlog("world", "利用状況の集計バッチを作成する", "open", (BACK,)),
        backlog("world", "ログ収集でタイムゾーンがずれる不具合を直す", "open", (BUG, BACK)),
    ],
]

ICEBOX_BACKLOGS: list[Backlog] = [
    backlog("hello", "ダークモードに対応する", "open", (FRONT,)),
    backlog("hello", "タスクを CSV でエクスポートする", "open"),
    backlog("hello", "カレンダー表示を追加する", "open", (FEATURE, FRONT)),
    backlog("hello", "Google カレンダーと連携する", "open", (FEATURE,)),
    backlog("hello", "モバイルアプリ（PWA）化する", "open"),
]

PROJECTS = ["hello", "world"]


def sprint_period(number: int) -> tuple[date, date]:
    start = FIRST_SPRINT_START + timedelta(days=SPRINT_DAYS * (number - 1))
    return start, start + timedelta(days=SPRINT_DAYS - 1)


def created_at(index: int) -> datetime:
    """集計期間の開始（8/6）より前の 7/21〜8/1 に、作った順で散らす。"""
    day = date(2026, 7, 21) + timedelta(days=index // 4)
    return datetime(day.year, day.month, day.day, 10 + (index % 4) * 2, tzinfo=TZ)


def closed_at(index: int, closed_on: date) -> datetime:
    return datetime(closed_on.year, closed_on.month, closed_on.day, 11 + index % 7, 30, tzinfo=TZ)


def rails_runner(code: str) -> str:
    """コンテナの中で gitlab-rails runner を実行し、標準出力を返す。失敗したら止まる。"""
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(EXAMPLE / "compose.yaml"),
            "exec",
            "-T",
            "gitlab",
            "gitlab-rails",
            "runner",
            code,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.exit(f"error: gitlab-rails runner が失敗しました\n{result.stdout}{result.stderr}")
    return result.stdout


def issue_root_token() -> str:
    """group colors がなければ root の token を発行する。あればエラーで止まり、何も変えない。"""
    output = rails_runner(
        f"""
        if Group.find_by_full_path({GROUP!r})
          puts 'GROUP_EXISTS'
        else
          root = User.find_by_username('root')
          token = root.personal_access_tokens.create!(
            name: 'seed_example', scopes: [:api, :sudo], expires_at: 365.days.from_now,
            organization: root.organizations.first || Organizations::Organization.first)
          puts "TOKEN=#{{token.token}}"
        end
        """
    )
    lines = output.splitlines()
    if "GROUP_EXISTS" in lines:
        sys.exit(
            f"error: group `{GROUP}` はすでにあります。"
            "立て直すときは docker compose -f example/compose.yaml down -v からやり直してください"
        )
    tokens = [line.removeprefix("TOKEN=") for line in lines if line.startswith("TOKEN=")]
    if not tokens:
        sys.exit(f"error: token を発行できませんでした\n{output}")
    return tokens[0]


class Api:
    def __init__(self, token: str) -> None:
        self._http = httpx.Client(base_url=f"{HOST}/api/v4", headers={"PRIVATE-TOKEN": token}, timeout=60)

    def get_list(self, path: str) -> list[Json]:
        result: list[Json] = self._send("GET", path, None, None)
        return result

    def post(self, path: str, data: Json, *, sudo: str | None = None) -> Json:
        result: Json = self._send("POST", path, data, sudo)
        return result

    def put(self, path: str, data: Json, *, sudo: str | None = None) -> Json:
        result: Json = self._send("PUT", path, data, sudo)
        return result

    def _send(self, method: str, path: str, data: Json | None, sudo: str | None) -> Any:
        headers = {"Sudo": sudo} if sudo else {}
        response = self._http.request(method, path, json=data, headers=headers)
        if not response.is_success:
            sys.exit(f"error: {method} {path} が失敗しました（HTTP {response.status_code}）: {response.text}")
        return response.json()


def seed(api: Api) -> list[Json]:
    """REST API でデータを作り、gitlab-rails runner で書き換える issue の情報を返す。"""
    users = {}
    for username in USERS:
        user = api.post(
            "/users",
            {
                "username": username,
                "name": username.capitalize(),
                "email": f"{username}@example.com",
                "force_random_password": True,
                "skip_confirmation": True,
            },
        )
        users[username] = user["id"]
        print(f"created user {username}", file=sys.stderr)

    group = api.post("/groups", {"name": GROUP, "path": GROUP, "visibility": "private"})
    for user_id in users.values():
        api.post(f"/groups/{group['id']}/members", {"user_id": user_id, "access_level": DEVELOPER})
    projects = {
        name: api.post("/projects", {"name": name, "path": name, "namespace_id": group["id"]})["id"]
        for name in PROJECTS
    }
    for name, color in LABELS.items():
        api.post(f"/groups/{group['id']}/labels", {"name": name, "color": color})
    milestones = {}
    for number in range(1, SPRINT_COUNT + 1):
        start, due = sprint_period(number)
        title = sprint_title(number)
        milestones[title] = api.post(
            f"/groups/{group['id']}/milestones",
            {"title": title, "start_date": start.isoformat(), "due_date": due.isoformat()},
        )["id"]
    milestones[ICEBOX] = api.post(f"/groups/{group['id']}/milestones", {"title": ICEBOX})["id"]
    print(f"created group {GROUP}, projects, labels, milestones", file=sys.stderr)

    planned = [(sprint_title(n), b) for n, sprint in enumerate(SPRINTS, 1) for b in sprint]
    planned += [(ICEBOX, b) for b in ICEBOX_BACKLOGS]
    fixes = []
    for index, (milestone, backlog) in enumerate(planned):
        author = USERS[index % len(USERS)]
        labels = list(backlog.labels)
        if backlog.state in ("ready", "doing", "review"):
            labels.insert(0, f"status::{backlog.state}")
        project_id = projects[backlog.project]
        issue = api.post(
            f"/projects/{project_id}/issues",
            {"title": backlog.title, "milestone_id": milestones[milestone], "labels": ",".join(labels)},
            sudo=author,
        )
        fix: Json = {
            "id": issue["id"],
            "created_at": created_at(index).isoformat(),
            "assignee_ids": [users[name] for name in backlog.assignees],
        }
        if backlog.closed_on:
            api.put(
                f"/projects/{project_id}/issues/{issue['iid']}",
                {"state_event": "close"},
                sudo=(backlog.assignees or (author,))[0],
            )
            fix["closed_at"] = closed_at(index, backlog.closed_on).isoformat()
        fixes.append(fix)
        print(f"created {backlog.project}#{issue['iid']} {backlog.title}", file=sys.stderr)
    return fixes


def rewrite_with_rails(fixes: list[Json]) -> None:
    """issue の created_at、closed_at（と close のイベントの日時）、担当者を書き換え、group の issue board を作る。

    CE では REST API でボードを作れないので、ここで作る（CE の group が持てるボードは1つ）。
    """
    payload = base64.b64encode(json.dumps(fixes).encode()).decode()
    rails_runner(
        f"""
        JSON.parse(Base64.decode64('{payload}')).each do |fix|
          issue = Issue.find(fix['id'])
          created = Time.iso8601(fix['created_at'])
          closed = fix['closed_at'] && Time.iso8601(fix['closed_at'])
          issue.update_columns(created_at: created, updated_at: closed || created, closed_at: closed)
          ResourceStateEvent.where(issue_id: issue.id).update_all(created_at: closed) if closed
          issue.assignee_ids = fix['assignee_ids']
        end
        group = Group.find_by_full_path({GROUP!r})
        Boards::CreateService.new(group, User.find_by_username('root')).execute if group.boards.empty?
        """
    )
    print(f"rewrote dates and assignees of {len(fixes)} issues", file=sys.stderr)


def arrange_board(api: Api) -> None:
    """group の issue board に、バックログ状態の順で status:: のリストを並べる（Open と Closed は最初からある）。"""
    boards = api.get_list(f"/groups/{GROUP}/boards")
    if not boards:
        sys.exit(f"error: group `{GROUP}` の issue board がありません")
    label_ids = {label["name"]: label["id"] for label in api.get_list(f"/groups/{GROUP}/labels")}
    for name in LABELS:
        if name.startswith("status::"):
            api.post(f"/groups/{GROUP}/boards/{boards[0]['id']}/lists", {"label_id": label_ids[name]})
    print(f"arranged board {boards[0]['name']}", file=sys.stderr)


def main() -> None:
    token = issue_root_token()
    TOKEN_FILE.write_text(token + "\n", encoding="utf-8")
    print(f"saved {TOKEN_FILE}", file=sys.stderr)
    api = Api(token)
    rewrite_with_rails(seed(api))
    arrange_board(api)


if __name__ == "__main__":
    main()
