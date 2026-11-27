"""Week dates (apps.delivery.calendar): pure functions, no database."""

import uuid
from datetime import date

from django.test import SimpleTestCase

from apps.delivery import calendar as cal


def _module(title: str, weeks: int) -> cal.ModuleIn:
    return cal.ModuleIn(
        uuid.uuid4(), title, tuple(cal.WeekIn(uuid.uuid4(), f"{title} W{i}") for i in range(weeks))
    )


class CalendarTest(SimpleTestCase):
    def test_plain_weeks_start_on_cohort_start_and_skip_weekends(self):
        m = _module("A", 3)
        plan = cal.build([m], start=date(2027, 1, 6))  # a Wednesday: week 1 is partial
        weeks = plan.modules[0].weeks
        self.assertEqual([w.number for w in weeks], [1, 2, 3])
        self.assertEqual((weeks[0].starts_on, weeks[0].ends_on), (date(2027, 1, 6), date(2027, 1, 8)))
        self.assertEqual((weeks[1].starts_on, weeks[1].ends_on), (date(2027, 1, 11), date(2027, 1, 15)))
        self.assertEqual(plan.end_date, date(2027, 1, 22))
        self.assertEqual(plan.breaks, [])

    def test_weekend_start_moves_to_monday(self):
        plan = cal.build([_module("A", 1)], start=date(2027, 1, 9))  # Saturday
        self.assertEqual(plan.modules[0].weeks[0].starts_on, date(2027, 1, 11))

    def test_bank_holiday_is_listed_on_the_week_not_skipped(self):
        plan = cal.build(
            [_module("A", 1)], start=date(2027, 5, 3), holidays={date(2027, 5, 3): "Early May bank holiday"}
        )
        week = plan.modules[0].weeks[0]
        self.assertEqual(week.starts_on, date(2027, 5, 4))  # first WORKING day
        self.assertEqual(
            [(d.date, d.title) for d in week.days_off], [(date(2027, 5, 3), "Early May bank holiday")]
        )

    def test_fully_closed_week_is_a_break_and_weeks_move_on(self):
        closure = cal.ClosureIn(date(2026, 12, 21), date(2027, 1, 1), "Christmas closure")
        plan = cal.build([_module("A", 2)], start=date(2026, 12, 14), closures=[closure])
        weeks = plan.modules[0].weeks
        self.assertEqual(weeks[0].starts_on, date(2026, 12, 14))
        self.assertEqual(weeks[1].starts_on, date(2027, 1, 4))  # two closed weeks skipped
        self.assertEqual([b.starts_on for b in plan.breaks], [date(2026, 12, 21), date(2026, 12, 28)])
        self.assertEqual(plan.breaks[0].reason, "Christmas closure")

    def test_modules_follow_each_other_and_override_moves_one(self):
        a, b, c = _module("A", 2), _module("B", 1), _module("C", 1)
        plan = cal.build([a, b, c], start=date(2027, 1, 4), overrides={c.module_key: date(2027, 3, 1)})
        self.assertEqual(plan.modules[1].starts_on, date(2027, 1, 18))  # straight after A
        self.assertEqual(plan.modules[2].starts_on, date(2027, 3, 1))
        self.assertEqual(plan.modules[2].override, date(2027, 3, 1))
        self.assertEqual(plan.warnings, [])

    def test_overlapping_override_is_allowed_with_a_warning(self):
        a, b = _module("A", 3), _module("B", 1)
        plan = cal.build([a, b], start=date(2027, 1, 4), overrides={b.module_key: date(2027, 1, 11)})
        self.assertEqual(plan.modules[1].starts_on, date(2027, 1, 11))
        self.assertEqual(len(plan.warnings), 1)

    def test_week_for_finds_the_running_week(self):
        plan = cal.build([_module("A", 2)], start=date(2027, 1, 4))
        self.assertEqual(plan.week_for(date(2027, 1, 16)).number, 2)  # Saturday of week 2
        self.assertIsNone(plan.week_for(date(2027, 2, 1)))

    def test_endless_closures_raise(self):
        closure = cal.ClosureIn(date(2027, 1, 1), date(2030, 1, 1), "Closed")
        with self.assertRaises(cal.CalendarError):
            cal.build([_module("A", 1)], start=date(2027, 1, 4), closures=[closure])

    def test_min_days_turns_a_short_week_into_a_break(self):
        # starts on a Thursday: 2 working days, below the provider's minimum of 3
        plan = cal.build([_module("A", 1)], start=date(2027, 1, 7), min_days=3)
        self.assertEqual(plan.modules[0].weeks[0].starts_on, date(2027, 1, 11))
        self.assertEqual(plan.breaks[0].reason, "Too few teaching days")
        with self.assertRaises(cal.CalendarError):
            cal.build([_module("A", 1)], start=date(2027, 1, 7), min_days=6)

    def test_this_or_next_week(self):
        plan = cal.build([_module("A", 2)], start=date(2027, 1, 4))
        self.assertEqual(plan.this_or_next_week(date(2026, 12, 1)).number, 1)  # before the start
        self.assertEqual(plan.this_or_next_week(date(2027, 1, 13)).number, 2)
        self.assertIsNone(plan.this_or_next_week(date(2027, 2, 1)))  # all over
