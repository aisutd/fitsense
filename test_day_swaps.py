"""Excuses and swaps (day_swaps.py) and how excused days count in the weekly adaptation (weekly_plan.py).

    python -m unittest test_day_swaps

The swap tests are Lane's (test_adaptive_week_two.py on the league-banners branch).
"""

from datetime import date
import unittest

import day_swaps
import weekly_plan as plans

recommender = plans.recommender


def logs(*entries):
    """("completed" | "skipped:no_equipment" | "skipped:no_time" ...) -> logs for days 1..n."""
    out = []
    for day, text in enumerate(entries, 1):
        status, _, reason = text.partition(":")
        log = {"day_number": day, "completion_status": status}
        if reason:
            log["skip_reason"] = reason
        out.append(log)
    return out


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

    def test_broken_equipment_swaps_only_the_exercises_that_need_it(self):
        _, swaps = day_swaps.swap_days(self.profile, self.plan, {2}, {"without": ["barbell"]}, self.exercises)
        barbell_on_day_2 = [i for i in self.plan["items"] if i["day"] == 2 and i["exercise"]["equipment"] == "barbell"]
        self.assertEqual(len(swaps), len(barbell_on_day_2))
        for swap in swaps:
            self.assertEqual(swap["day"], 2)
            self.assertNotEqual(swap["new"]["equipment"], "barbell")
            self.assertEqual(swap["group"], recommender.muscle_group(swap["new"]))

    def test_progress_is_kept(self):
        _, swaps = day_swaps.swap_days(self.profile, self.plan, {2}, {"without": ["barbell"]}, self.exercises)
        for swap in swaps:
            self.assertEqual(swap["new_dose"], swap["old_dose"])   # 3 sets x 10 reps stays

    def test_cant_make_it_to_the_gym_uses_what_is_at_home(self):
        new_plan, _ = day_swaps.swap_days(self.profile, self.plan, {1}, {"location": "home", "equipment": ["dumbbell"]}, self.exercises)
        for item in new_plan["items"]:
            if item["day"] == 1:
                self.assertIn(item["exercise"]["equipment"], recommender.NO_EQUIPMENT | {"dumbbell"})

    def test_the_rest_of_the_week_changes_every_day_given(self):
        _, one_day = day_swaps.swap_days(self.profile, self.plan, {1}, {"without": ["barbell"]}, self.exercises)
        _, week = day_swaps.swap_days(self.profile, self.plan, {1, 2, 3, 4}, {"without": ["barbell"]}, self.exercises)
        barbell_days = {i["day"] for i in self.plan["items"] if i["exercise"]["equipment"] == "barbell"}
        self.assertEqual({s["day"] for s in week}, barbell_days)
        self.assertLess(len(one_day), len(week))

    def test_other_days_are_untouched(self):
        new_plan, _ = day_swaps.swap_days(self.profile, self.plan, {1}, {"location": "outdoors"}, self.exercises)
        self.assertEqual([i for i in new_plan["items"] if i["day"] != 1], [i for i in self.plan["items"] if i["day"] != 1])

    def test_a_named_exercise_is_swapped_on_request(self):
        name = next(i for i in self.plan["items"] if i["day"] == 1)["exercise"]["name"]
        _, swaps = day_swaps.swap_days(self.profile, self.plan, {1}, {}, self.exercises, [name])
        self.assertEqual([s["old"]["name"] for s in swaps], [name])
        self.assertEqual(swaps[0]["reason"], "you asked to swap it")


class ExcusedDaysTests(unittest.TestCase):
    profile = {"user_id": "u1", "name": "Sam", "age": 29, "fitness_level": "intermediate",
               "fitness_goal": "build_muscle", "workout_location": "gym", "workout_frequency": 4,
               "equipment": [], "workout_preferences": [], "points": 0}
    plan = {"week_start": date(2026, 10, 26), "days": 4, "items": []}

    def test_excused_days_are_left_out_of_the_week(self):
        week = logs("completed", "completed", "completed", "skipped:no_equipment")
        self.assertEqual(plans.excused_days(self.plan, week), {4})
        self.assertEqual(plans.completion_rate(self.plan, week), 1.0)
        self.assertEqual(plans.adapt(self.profile, self.plan, week)["change"], "progress")

    def test_other_skip_reasons_still_count(self):
        week = logs("completed", "completed", "completed", "skipped:no_time")
        self.assertEqual(plans.excused_days(self.plan, week), set())
        self.assertEqual(plans.completion_rate(self.plan, week), 0.75)
        self.assertNotEqual(plans.adapt(self.profile, self.plan, week)["change"], "progress")

    def test_a_fully_excused_week_keeps_the_plan(self):
        week = logs("skipped:location", "skipped:location", "skipped:no_equipment", "skipped:location")
        result = plans.adapt(self.profile, self.plan, week)
        self.assertEqual((result["change"], result["days"]), ("same dose", 4))

    def test_an_excused_day_that_was_done_anyway_is_just_done(self):
        week = logs("completed", "completed", "completed", "skipped:no_equipment") + [
            {"day_number": 4, "completion_status": "completed"}]
        self.assertEqual(plans.excused_days(self.plan, week), set())


if __name__ == "__main__":
    unittest.main()
