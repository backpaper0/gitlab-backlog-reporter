"""例の環境（group colors）のスナップショットからレポート全体を作り、期待ファイルと突き合わせる。

スナップショットは scripts/record_fixtures.py で取り直す。期待ファイルは `UPDATE_GOLDEN=1 uv run pytest` で更新する。
"""

import json
import os
from datetime import date
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from gitlab_backlog_reporter.cli import RunResult, run
from tests.gitlab_fake import FakeGitLab

SNAPSHOT = Path(__file__).parent / "fixtures" / "colors"
EXPECTED = Path(__file__).parent / "golden" / "colors.md"

# スナップショットを取った日。期の途中（Iteration-Q3-1 の2日目）にあたる。
TODAY = date(2026, 10, 2)
TZ = ZoneInfo("Asia/Tokyo")
ENV = {"GITLAB_HOST": "http://localhost:9080", "GITLAB_PRIVATE_TOKEN": "dummy"}


def load(name: str) -> Any:
    return json.loads((SNAPSHOT / f"{name}.json").read_text(encoding="utf-8"))


def test_colors_report_matches_golden() -> None:
    fake = FakeGitLab(load("group"), load("milestones"), load("issues"))

    result = run(["colors"], ENV, TODAY, TZ, fake.transport())

    assert (result.stderr, result.exit_code) == ("", 0)
    if os.environ.get("UPDATE_GOLDEN") == "1":
        EXPECTED.parent.mkdir(exist_ok=True)
        EXPECTED.write_text(result.stdout, encoding="utf-8")
    assert result == RunResult(EXPECTED.read_text(encoding="utf-8"), "", 0)
