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
from gitlab_backlog_reporter.gitlab import GitLabClient, read_connection
from gitlab_backlog_reporter.holidays import read_holidays
from gitlab_backlog_reporter.report import ReportContext, render


@dataclass(frozen=True)
class RunResult:
    stdout: str
    stderr: str
    exit_code: int


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gbr",
        description="GitLab の group か project のバックログとスプリントの進捗を Markdown のレポートにする",
    )
    parser.add_argument(
        "path",
        help="集計範囲の full path（数値だけなら id）。--project を付けなければ group、付ければ project",
    )
    parser.add_argument("--project", action="store_true", help="位置引数を group ではなく project として解釈する")
    parser.add_argument(
        "-o", "--output", metavar="PATH", help="レポートを書くファイル（既存のファイルは上書き）。デフォルトは標準出力"
    )
    parser.add_argument(
        "--sprint-prefix",
        default="Iteration-",
        help="スプリントとする、集計範囲の milestone の名前の prefix（デフォルト: %(default)s）",
    )
    parser.add_argument(
        "--exclude-sprint-prefix",
        action="append",
        default=[],
        metavar="PREFIX",
        help="スプリントから除外する、集計範囲の milestone の名前の prefix。繰り返し指定できる",
    )
    parser.add_argument(
        "--icebox", default="Icebox", help="Icebox とする、集計範囲の milestone の名前（デフォルト: %(default)s）"
    )
    parser.add_argument(
        "--no-report-warnings",
        action="store_true",
        help="レポートに warning を書かない（標準エラー出力には書く）",
    )
    parser.add_argument("--no-icebox-list", action="store_true", help="バックログ一覧に Icebox のセクションを書かない")
    parser.add_argument(
        "--holidays",
        metavar="PATH",
        help="休業日（土日以外の休日）を1行に1日付 YYYY-MM-DD で書いたファイル。休日だけのスプリントの隙間は警告しない",
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
        holidays = frozenset() if args.holidays is None else read_holidays(args.holidays)
        with GitLabClient(connection, transport) as client:
            scope = client.scope("project" if args.project else "group", args.path)
            milestones = client.milestones(scope)
            issues = client.issues(scope)
        backlog = collect_backlog(
            milestones,
            issues,
            args.sprint_prefix,
            tuple(args.exclude_sprint_prefix),
            args.icebox,
            scope,
            holidays,
        )
    except ReportError as e:
        return RunResult("", "".join(f"error: {m}\n" for m in e.messages), 1)

    context = ReportContext(
        connection.host,
        scope,
        today,
        tz,
        show_warnings=not args.no_report_warnings,
        show_icebox_list=not args.no_icebox_list,
    )
    report = render(backlog, context)
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
