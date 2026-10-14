"""GitLab REST API (v4) の薄いクライアント。

使うのは集計範囲そのもの、その milestones、その issues だけ。集計範囲が group なら group、group milestones、
group issues（subgroup を含む）、project なら project、project milestones（祖先の group milestone を含まない）、
project issues。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote

import httpx

from gitlab_backlog_reporter.errors import ReportError

type Json = dict[str, Any]

PER_PAGE = 100


class GitLabError(ReportError):
    pass


type ScopeKind = Literal["group", "project"]


@dataclass(frozen=True)
class Scope:
    """集計範囲。"""

    kind: ScopeKind
    id: int
    full_path: str

    @property
    def milestone_kind(self) -> str:
        """集計範囲の milestone の呼び名。group なら group milestone、project なら project milestone。"""
        return f"{self.kind} milestone"

    def is_same_kind(self, milestone: Json) -> bool:
        """milestone が集計範囲と同じ種類（group milestone か project milestone）か。どの group や project のものかは見ない。"""
        return milestone.get(f"{self.kind}_id") is not None


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

    def scope(self, kind: ScopeKind, path: str) -> Scope:
        """path は full path か、数値だけなら id。"""
        params = {"with_projects": "false"} if kind == "group" else {}
        response = self._get(
            _scope_path(kind, path),
            params,
            not_found=f"{kind} `{path}` が見つからないか、token にアクセス権がありません",
        )
        result: Json = response.json()
        full_path = result["full_path"] if kind == "group" else result["path_with_namespace"]
        return Scope(kind, result["id"], full_path)

    def milestones(self, scope: Scope) -> list[Json]:
        return self._get_all(f"{_scope_path(scope.kind, str(scope.id))}/milestones", {})

    def issues(self, scope: Scope) -> list[Json]:
        params = (
            {"include_subgroups": "true", "state": "all", "scope": "all"}
            if scope.kind == "group"
            else {"state": "all"}
        )
        return self._get_all(f"{_scope_path(scope.kind, str(scope.id))}/issues", params)

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


def _scope_path(kind: ScopeKind, path: str) -> str:
    return f"/{kind}s/{quote(path, safe='')}"
