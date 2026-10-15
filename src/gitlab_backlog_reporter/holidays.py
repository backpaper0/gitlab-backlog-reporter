"""休日の判定と、休業日のファイルの読み込み。"""

import re
from datetime import date

from gitlab_backlog_reporter.errors import ReportError

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def is_holiday(day: date, holidays: frozenset[date]) -> bool:
    """土曜日、日曜日、それに休業日。"""
    return day.weekday() >= 5 or day in holidays


def read_holidays(path: str) -> frozenset[date]:
    """1行に1日付を YYYY-MM-DD で書いたファイルを読む。空行は読み飛ばし、`#` から行末まではコメントとする。

    土日、重複、集計期間の外の日付もそのまま受け付ける。解釈できない行はすべてまとめてエラーにする。
    """
    try:
        with open(path, encoding="utf-8-sig") as f:  # BOM 付きでも読めるように
            lines = f.read().splitlines()
    except (OSError, UnicodeDecodeError) as e:
        reason = e.strerror if isinstance(e, OSError) and e.strerror else str(e)
        raise ReportError(f"休業日のファイル {path} を読めません（{reason}）") from e
    holidays = set()
    messages = []
    for number, line in enumerate(lines, start=1):
        text = line.split("#", 1)[0].strip()
        if not text:
            continue
        day = _parse(text)
        if day is None:
            messages.append(
                f"休業日のファイル {path} の {number} 行目を日付として解釈できません（YYYY-MM-DD で書いてください）: {text}"
            )
        else:
            holidays.add(day)
    if messages:
        raise ReportError(*messages)
    return frozenset(holidays)


def _parse(text: str) -> date | None:
    if not _DATE.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None
