"""テスト用の GitLab REST API。API の JSON の形をした dict を作るビルダー関数と、それを返す MockTransport。"""

import itertools
from collections.abc import Callable
from typing import Any
from urllib.parse import unquote

import httpx

type Json = dict[str, Any]

_ids = itertools.count(1)


def make_group(full_path: str = "colors", id: int = 10) -> Json:
    return {"id": id, "name": full_path.rsplit("/", 1)[-1], "full_path": full_path}


def make_project(full_path: str = "colors/red", id: int = 20) -> Json:
    return {"id": id, "name": full_path.rsplit("/", 1)[-1], "path_with_namespace": full_path}


def make_milestone(
    title: str,
    start_date: str | None = None,
    due_date: str | None = None,
    *,
    group_id: int | None = 10,
    project_id: int | None = None,
    state: str = "active",
) -> Json:
    milestone: Json = {
        "id": next(_ids),
        "iid": 1,
        "title": title,
        "state": state,
        "start_date": start_date,
        "due_date": due_date,
    }
    if project_id is not None:
        milestone["project_id"] = project_id
    else:
        milestone["group_id"] = group_id
    return milestone


def make_issue(
    milestone: Json | None,
    *,
    closed_at: str | None = None,
    labels: list[str] | None = None,
    project: str = "colors/rainbow",
    title: str = "issue",
    assignees: list[str] | None = None,
    iid: int | None = None,
) -> Json:
    iid = iid or next(_ids)
    return {
        "id": iid + 1000,
        "iid": iid,
        "project_id": 1,
        "title": title,
        "state": "closed" if closed_at else "opened",
        "closed_at": closed_at,
        "labels": labels or [],
        "milestone": milestone,
        "assignees": [{"username": u} for u in assignees or []],
        "references": {"relative": f"{project.rsplit('/', 1)[-1]}#{iid}", "full": f"{project}#{iid}"},
        "web_url": f"http://gitlab.test/{project}/-/issues/{iid}",
    }


class FakeGitLab:
    """集計範囲1つについて、その集計範囲、milestones、issues の3つのエンドポイントだけを持つ GitLab。

    集計範囲は make_group か make_project で作る。project なら `/projects/...`、group なら `/groups/...` に答える。
    """

    def __init__(
        self,
        scope: Json,
        milestones: list[Json],
        issues: list[Json],
        *,
        per_page: int = 100,
    ) -> None:
        self.scope = scope
        self.milestones = milestones
        self.issues = issues
        self.per_page = per_page
        self.requests: list[httpx.Request] = []
        self.failures: dict[str, int] = {}

    def fail(self, endpoint: str, status: int) -> FakeGitLab:
        """`scope`、`milestones`、`issues` のいずれかを status で失敗させる。"""
        self.failures[endpoint] = status
        return self

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = unquote(request.url.raw_path.decode().split("?", 1)[0])
        if "path_with_namespace" in self.scope:
            prefix, full_path, not_found = "/api/v4/projects/", self.scope["path_with_namespace"], "Project"
        else:
            prefix, full_path, not_found = "/api/v4/groups/", self.scope["full_path"], "Group"
        if not path.startswith(prefix):
            return httpx.Response(404, json={"message": f"404 {not_found} Not Found"})
        rest = path.removeprefix(prefix)
        routes: dict[str, Callable[[], httpx.Response]] = {}
        for gid in (full_path, str(self.scope["id"])):
            routes[gid] = lambda: self._respond("scope", lambda: httpx.Response(200, json=self.scope))
            routes[f"{gid}/milestones"] = lambda: self._respond(
                "milestones", lambda: self._paged(request, self.milestones)
            )
            routes[f"{gid}/issues"] = lambda: self._respond("issues", lambda: self._paged(request, self.issues))
        if rest not in routes:
            return httpx.Response(404, json={"message": f"404 {not_found} Not Found"})
        return routes[rest]()

    def _respond(self, endpoint: str, ok: Callable[[], httpx.Response]) -> httpx.Response:
        if endpoint in self.failures:
            return httpx.Response(self.failures[endpoint], json={"message": "failed"})
        return ok()

    def _paged(self, request: httpx.Request, items: list[Json]) -> httpx.Response:
        per_page = min(int(request.url.params.get("per_page", "20")), self.per_page)
        page = int(request.url.params.get("page", "1"))
        start = (page - 1) * per_page
        has_next = start + per_page < len(items)
        headers = {"x-next-page": str(page + 1) if has_next else ""}
        return httpx.Response(200, json=items[start : start + per_page], headers=headers)
