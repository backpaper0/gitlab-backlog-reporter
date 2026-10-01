"""GitLab REST API (v4) の薄いクライアント。使うのは group、group milestones、group issues だけ。"""

from typing import Any
from urllib.parse import quote

import httpx

from gitlab_backlog_reporter.errors import ReportError

type Json = dict[str, Any]

PER_PAGE = 100


class GitLabError(ReportError):
    pass


def normalize_host(host: str) -> str:
    """scheme がなければ `https://` を補い、末尾の `/` を落とす。"""
    if "://" not in host:
        host = f"https://{host}"
    return host.rstrip("/")


class GitLabClient:
    def __init__(self, host: str, token: str, transport: httpx.BaseTransport) -> None:
        self._http = httpx.Client(
            base_url=f"{normalize_host(host)}/api/v4",
            headers={"PRIVATE-TOKEN": token},
            transport=transport,
        )

    def __enter__(self) -> "GitLabClient":
        return self

    def __exit__(self, *_: object) -> None:
        self._http.close()

    def group(self, group: str) -> Json:
        response = self._get(
            _group_path(group),
            {"with_projects": "false"},
            not_found=f"group `{group}` が見つからないか、token にアクセス権がありません",
        )
        result: Json = response.json()
        return result

    def group_milestones(self, group_id: int) -> list[Json]:
        return self._get_all(f"{_group_path(str(group_id))}/milestones", {})

    def group_issues(self, group_id: int) -> list[Json]:
        return self._get_all(
            f"{_group_path(str(group_id))}/issues",
            {"include_subgroups": "true", "state": "all", "scope": "all"},
        )

    def _get_all(self, path: str, params: dict[str, str]) -> list[Json]:
        items: list[Json] = []
        page = "1"
        while page:
            response = self._get(path, {**params, "per_page": str(PER_PAGE), "page": page})
            items.extend(response.json())
            page = response.headers.get("x-next-page", "")
        return items

    def _get(
        self, path: str, params: dict[str, str] | None = None, *, not_found: str | None = None
    ) -> httpx.Response:
        response = self._http.get(path, params=params)
        if response.status_code == 401:
            raise GitLabError("token が無効か、期限切れです")
        if response.status_code == 404 and not_found:
            raise GitLabError(not_found)
        response.raise_for_status()
        return response


def _group_path(group: str) -> str:
    return f"/groups/{quote(group, safe='')}"
