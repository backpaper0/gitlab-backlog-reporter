"""例の環境から group、group milestones、group issues の API レスポンスを保存し、golden test のスナップショットにする。

使い方: uv run scripts/record_fixtures.py [group] [保存先]（デフォルトは colors と tests/fixtures/colors）

接続先は gbr と同じく GITLAB_HOST と GITLAB_PRIVATE_TOKEN から読む。token はリクエストにしか使わないので、保存されない。
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

from gitlab_backlog_reporter.cli import read_connection
from gitlab_backlog_reporter.errors import ReportError
from gitlab_backlog_reporter.gitlab import GitLabClient


def scrub(data: Any) -> Any:
    """runners_token のような、名前が token で終わるキーを取り除く。"""
    if isinstance(data, dict):
        return {k: scrub(v) for k, v in data.items() if not k.endswith("token")}
    if isinstance(data, list):
        return [scrub(v) for v in data]
    return data


def main() -> None:
    group_path = sys.argv[1] if len(sys.argv) > 1 else "colors"
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "tests/fixtures/colors")
    try:
        connection = read_connection(os.environ)
        with GitLabClient(connection.host, connection.token, httpx.HTTPTransport()) as client:
            group = client.group(group_path)
            snapshot = {
                "group": group,
                "milestones": client.group_milestones(group["id"]),
                "issues": client.group_issues(group["id"]),
            }
    except ReportError as e:
        for message in e.messages:
            print(f"error: {message}", file=sys.stderr)
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, data in snapshot.items():
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(scrub(data), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"saved {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
