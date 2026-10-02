"""バーンダウンの数式（時間軸、理想線、予定線、実績線、丸め）を純粋な関数として確かめる。"""

from datetime import date
from decimal import Decimal
from fractions import Fraction

from gitlab_backlog_reporter.burndown import SprintLoad, actual_at, ideal_at, planned_at, round1, weekly_points


def test_points_are_every_seven_days_ending_the_day_after_the_last_sprint() -> None:
    assert weekly_points(date(2026, 10, 1), date(2026, 10, 28)) == [
        date(2026, 10, 1),
        date(2026, 10, 8),
        date(2026, 10, 15),
        date(2026, 10, 22),
        date(2026, 10, 29),
    ]


def test_last_point_is_kept_when_period_is_not_a_multiple_of_seven_days() -> None:
    assert weekly_points(date(2026, 10, 1), date(2026, 10, 10)) == [
        date(2026, 10, 1),
        date(2026, 10, 8),
        date(2026, 10, 11),
    ]


def test_ideal_line_falls_linearly_from_total_to_zero() -> None:
    start, finish = date(2026, 10, 1), date(2026, 10, 29)

    assert ideal_at(31, start, finish, start) == 31
    assert ideal_at(31, start, finish, date(2026, 10, 15)) == Fraction(31, 2)
    assert ideal_at(31, start, finish, finish) == 0


def test_ideal_line_is_clamped_outside_the_period() -> None:
    start, finish = date(2026, 10, 1), date(2026, 10, 29)

    assert ideal_at(31, start, finish, date(2026, 9, 1)) == 31
    assert ideal_at(31, start, finish, date(2026, 12, 1)) == 0


def test_planned_line_consumes_each_sprint_linearly_within_its_own_period() -> None:
    sprints = [
        SprintLoad(4, date(2026, 10, 1), date(2026, 10, 14)),
        SprintLoad(6, date(2026, 10, 15), date(2026, 10, 28)),
    ]

    assert planned_at(sprints, date(2026, 10, 1)) == 10
    assert planned_at(sprints, date(2026, 10, 8)) == 8
    assert planned_at(sprints, date(2026, 10, 15)) == 6
    assert planned_at(sprints, date(2026, 10, 22)) == 3
    assert planned_at(sprints, date(2026, 10, 29)) == 0
    assert planned_at(sprints, date(2026, 9, 1)) == 10
    assert planned_at(sprints, date(2026, 12, 1)) == 0


def test_planned_line_is_flat_in_a_gap_between_sprints() -> None:
    sprints = [
        SprintLoad(4, date(2026, 10, 1), date(2026, 10, 7)),
        SprintLoad(6, date(2026, 10, 15), date(2026, 10, 21)),
    ]

    assert planned_at(sprints, date(2026, 10, 8)) == 6
    assert planned_at(sprints, date(2026, 10, 12)) == 6
    assert planned_at(sprints, date(2026, 10, 15)) == 6


def test_actual_line_counts_issues_closed_before_the_point() -> None:
    closed_on = [date(2026, 9, 20), date(2026, 10, 7), date(2026, 10, 8)]

    assert actual_at(10, closed_on, date(2026, 10, 1)) == 9
    assert actual_at(10, closed_on, date(2026, 10, 8)) == 8
    assert actual_at(10, closed_on, date(2026, 10, 9)) == 7


def test_values_are_rounded_half_up_to_one_decimal_place() -> None:
    assert round1(Fraction(31 * 11, 12)) == Decimal("28.4")
    assert round1(Fraction(1, 4)) == Decimal("0.3")
    assert round1(Fraction(31)) == Decimal("31.0")
