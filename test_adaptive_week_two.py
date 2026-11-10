"""Swap-aware weekly adaptation and same-day swaps (adaptive_week_two.py + weekly_plan.py).

    python -m unittest test_adaptive_week_two
"""

from datetime import date
from pathlib import Path
import tempfile
import unittest

import adaptive_week_two as awt
import weekly_plan as plans

recommender = plans.recommender


def logs(*entries):
    """("completed" | "skipped:no_equipment" | "completed:swapped", ...) -> logs for days 1..n."""
    out = []
    for day, text in enumerate(entries, 1):
        status, _, tag = text.partition(":")
        log = {"day_number": day, "completion_status": status}
        if tag == "swapped":
            log["swapped"] = True
        elif tag:
            log["skip_reason"] = tag
        out.append(log)
    return out


class SwapAwareAdaptationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exercises = recommender.load_exercises()
        cls.profile = {"user_id": "u1", "name": "Sam", "age": 29, "fitness_level": "intermediate",
                       "fitness_goal": "build_muscle", "workout_location": "gym", "workout_frequency": 4,
                       "equipment": [], "workout_preferences": [], "points": 0}
        cls.week_one = plans.first_week(cls.profile, cls.exercises, date(2026, 10, 26))

    def test_an_equipment_skip_is_not_a_missed_workout(self):
        week = logs("completed", "completed:swapped", "skipped:no_equipment", "completed")
        details = plans.adaptation_details(self.profile, self.week_one, week)
        self.assertEqual(details["original_rule"], "same dose")   # what the old rule would have said
        self.assertEqual(details["decision"], "progress")
        self.assertEqual(details["equipment_skips"], [3])
        self.assertEqual(details["swapped"], [2])

    def test_an_ordinary_skip_still_counts(self):
        decision, days = plans.adaptation(self.profile, self.week_one, logs("completed", "completed", "skipped", "completed"))
        self.assertEqual((decision, days), ("same dose", 4))

    def test_without_skip_reasons_it_matches_the_original_rules(self):
        for week in (logs(*["completed"] * 4), logs("completed", "partial", "skipped", "skipped"),
                     logs("skipped", "skipped", "skipped", "skipped")):
            statuses = plans.day_statuses(self.week_one, week)
            rate = plans.completion_rate(self.week_one, week)
            expected = ("progress" if rate >= 0.9 and "skipped" not in statuses.values()
                        else "same dose" if rate >= 0.6 else "reduce")
            self.assertEqual(plans.adaptation(self.profile, self.week_one, week)[0], expected)

    def test_an_equipment_blocked_days_exercises_are_kept(self):
        week = logs("completed", "completed", "skipped:no_equipment", "completed")
        next_plan = plans.next_week(self.profile, self.exercises, self.week_one, week)
        before = {i["exercise"]["id"] for i in self.week_one["items"] if i["day"] == 3}
        after = {i["exercise"]["id"] for i in next_plan["items"]}
        self.assertTrue(before <= after)
        self.assertEqual(next_plan["adaptation"]["decision"], "progress")

    def test_seven_day_players_keep_a_recovery_day(self):
        busy = {**self.profile, "workout_frequency": 7}
        week_one = plans.first_week(busy, self.exercises, date(2026, 10, 26))
        decision, days = plans.adaptation(busy, week_one, logs(*["completed"] * week_one["days"]))
        self.assertEqual(decision, "progress")
        self.assertLessEqual(days, plans.MAX_TRAINING_DAYS)

    def test_format_plan_says_how_the_week_was_decided(self):
        week = logs("completed", "completed", "skipped:no_equipment", "completed")
        text = plans.format_plan(self.profile, plans.next_week(self.profile, self.exercises, self.week_one, week))
        self.assertIn("Adapted from last week: progress", text)
        self.assertIn("not counted as missed", text)

    def test_no_model_file_means_rules_only(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(awt.load_model(Path(folder) / "missing.json"))


class SameDaySwapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exercises = recommender.load_exercises()
        cls.profile = {"user_id": "u1", "name": "Sam", "age": 29, "fitness_level": "intermediate",
                       "fitness_goal": "build_muscle", "workout_location": "gym", "workout_frequency": 4,
                       "equipment": [], "workout_preferences": [], "points": 0}
        cls.plan = plans.first_week(cls.profile, cls.exercises, date(2026, 10, 26))
        for item in cls.plan["items"]:
            if item["reps"]:
                item["reps"] = 10   # progress already reached

    def test_no_barbell_today_swaps_only_barbell_exercises_on_that_day(self):
        _, swaps = awt.swap_days(self.profile, self.plan, {2}, {"without": ["barbell"]}, self.exercises)
        barbell_on_day_2 = [i for i in self.plan["items"] if i["day"] == 2 and i["exercise"]["equipment"] == "barbell"]
        self.assertEqual(len(swaps), len(barbell_on_day_2))
        for swap in swaps:
            self.assertEqual(swap["day"], 2)
            self.assertNotEqual(swap["new"]["equipment"], "barbell")
            self.assertEqual(swap["group"], recommender.muscle_group(swap["new"]))

    def test_progress_is_kept(self):
        _, swaps = awt.swap_days(self.profile, self.plan, {2}, {"without": ["barbell"]}, self.exercises)
        for swap in swaps:
            self.assertEqual(swap["new_dose"], swap["old_dose"])   # 3 sets x 10 reps stays

    def test_at_home_today_uses_only_what_is_there(self):
        new_plan, _ = awt.swap_days(self.profile, self.plan, {1}, {"location": "home", "equipment": ["dumbbell"]}, self.exercises)
        for item in new_plan["items"]:
            if item["day"] == 1:
                self.assertIn(item["exercise"]["equipment"], recommender.NO_EQUIPMENT | {"dumbbell"})

    def test_other_days_are_untouched(self):
        new_plan, _ = awt.swap_days(self.profile, self.plan, {1}, {"location": "outdoors"}, self.exercises)
        self.assertEqual([i for i in new_plan["items"] if i["day"] != 1], [i for i in self.plan["items"] if i["day"] != 1])

    def test_a_named_exercise_is_swapped_on_request(self):
        name = next(i for i in self.plan["items"] if i["day"] == 1)["exercise"]["name"]
        _, swaps = awt.swap_days(self.profile, self.plan, {1}, {}, self.exercises, [name])
        self.assertEqual([s["old"]["name"] for s in swaps], [name])
        self.assertEqual(swaps[0]["reason"], "user asked to swap it")


if __name__ == "__main__":
    unittest.main()
