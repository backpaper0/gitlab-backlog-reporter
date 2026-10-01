import argparse
import contextlib
import io
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, tzinfo

import httpx

from gitlab_backlog_reporter.backlog import collect_backlog
from gitlab_backlog_reporter.errors import ReportError
from gitlab_backlog_reporter.gitlab import GitLabClient, normalize_host
from gitlab_backlog_reporter.report import ReportContext, render


@dataclass(frozen=True)
class RunResult:
    stdout: str
    stderr: str
    exit_code: int


@dataclass(frozen=True)
class Connection:
    host: str
    token: str


def read_connection(env: Mapping[str, str]) -> Connection:
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
    return Connection(host, token)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gbr",
        description="GitLab の group のバックログとスプリントの進捗を Markdown のレポートにする",
    )
    parser.add_argument("group", help="group の full path（数値だけなら id）")
    parser.add_argument(
        "-o", "--output", metavar="PATH", help="レポートを書くファイル（既存のファイルは上書き）。デフォルトは標準出力"
    )
    parser.add_argument(
        "--sprint-prefix", default="Iteration-", help="スプリントとする group milestone の名前の prefix（デフォルト: %(default)s）"
    )
    parser.add_argument(
        "--icebox", default="Icebox", help="Icebox とする group milestone の名前（デフォルト: %(default)s）"
    )
    return parser


def run(
    argv: Sequence[str],
    env: Mapping[str, str],
    today: date,
    tz: tzinfo,
    transport: httpx.BaseTransport,
) -> RunResult:
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            args = build_parser().parse_args(argv)
    except SystemExit as e:
        return RunResult(stdout.getvalue(), stderr.getvalue(), e.code if isinstance(e.code, int) else 2)

    try:
        connection = read_connection(env)
        with GitLabClient(connection.host, connection.token, transport) as client:
            group = client.group(args.group)
            milestones = client.group_milestones(group["id"])
            issues = client.group_issues(group["id"])
        backlog = collect_backlog(milestones, issues, args.sprint_prefix, args.icebox, group["full_path"])
    except ReportError as e:
        return RunResult("", "".join(f"error: {m}\n" for m in e.messages), 1)

    report = render(backlog, ReportContext(normalize_host(connection.host), group["full_path"], today))
    warnings = "".join(f"warning: {w}\n" for w in backlog.warnings)
    if args.output is None:
        return RunResult(report, warnings, 0)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report)
    return RunResult("", warnings, 0)


def main() -> None:
    now = datetime.now().astimezone()
    tz = now.tzinfo
    assert tz is not None
    result = run(sys.argv[1:], os.environ, now.date(), tz, httpx.HTTPTransport())
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    sys.exit(result.exit_code)
