"""GitLab REST API (v4) の薄いクライアント。使うのは group、group milestones、group issues だけ。"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from gitlab_backlog_reporter.errors import ReportError

type Json = dict[str, Any]

PER_PAGE = 100


class GitLabError(ReportError):
    pass


@dataclass(frozen=True)
class Connection:
    host: str
    """scheme を含み、末尾に `/` を持たない URL。"""
    token: str


def read_connection(env: Mapping[str, str]) -> Connection:
    """GITLAB_HOST と GITLAB_PRIVATE_TOKEN を読む。空文字は未設定と同じに扱い、足りないものをまとめて報告する。"""
    host = env.get("GITLAB_HOST", "")
    token = env.get("GITLAB_PRIVATE_TOKEN", "")
    missing = []
    if not host:
        missing.append(
            "環境変数 GITLAB_HOST が設定されていません。"
            "接続先の GitLab の URL を設定してください（例: GITLAB_HOST=https://gitlab.example.com）"
        )
    if not token:
        missing.append(
            "環境変数 GITLAB_PRIVATE_TOKEN が設定されていません。"
            "read_api スコープを持つ personal access token を設定してください"
        )
    if missing:
        raise ReportError(*missing)
    if "://" not in host:
        host = f"https://{host}"
    return Connection(host.rstrip("/"), token)


class GitLabClient:
    def __init__(self, connection: Connection, transport: httpx.BaseTransport) -> None:
        self._http = httpx.Client(
            base_url=f"{connection.host}/api/v4",
            headers={"PRIVATE-TOKEN": connection.token},
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
        """失敗したらリトライせずに GitLabError にする。メッセージに URL は出すが、ヘッダーで送る token は出さない。"""
        try:
            response = self._http.get(path, params=params)
        except httpx.TransportError as e:
            raise GitLabError(f"GitLab API に接続できませんでした（{e}）: GET {e.request.url}") from e
        if response.status_code == 401:
            raise GitLabError("token が無効か、期限切れです")
        if response.status_code == 404 and not_found:
            raise GitLabError(not_found)
        if not response.is_success:
            raise GitLabError(
                f"GitLab API がエラーを返しました（HTTP {response.status_code}）: GET {response.request.url}"
            )
        return response


def _group_path(group: str) -> str:
    return f"/groups/{quote(group, safe='')}"
