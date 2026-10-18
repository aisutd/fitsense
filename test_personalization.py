import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('prototype', ROOT / 'Fitsense-Issue-5.py')
prototype = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prototype)


class PersonalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exercises = prototype.load_exercises()
        cls.base = {'age': 30, 'fitness_level': 'beginner', 'fitness_goal': 'build_muscle',
                    'workout_location': 'home', 'workout_frequency': 3, 'equipment': []}

    def recommend(self, **changes):
        return prototype.recommend_exercises({**self.base, **changes}, self.exercises)

    @staticmethod
    def flat(result):
        return [exercise for group in result.values() for exercise in group]

    def test_level_is_never_above_user(self):
        for level in ('beginner', 'intermediate', 'advanced'):
            for exercise in self.flat(self.recommend(fitness_level=level, workout_location='gym')):
                self.assertLessEqual(prototype.LEVEL_RANK[exercise['level']], prototype.LEVEL_RANK[level])

    def test_level_changes_exercises(self):
        beginner = {e['id'] for e in self.flat(self.recommend())}
        advanced = {e['id'] for e in self.flat(self.recommend(fitness_level='advanced'))}
        self.assertNotEqual(beginner, advanced)

    def test_home_without_equipment_is_bodyweight_only(self):
        for exercise in self.flat(self.recommend(fitness_level='advanced')):
            self.assertIn(exercise['equipment'], prototype.NO_EQUIPMENT)

    def test_saved_equipment_unlocks_exercises(self):
        with_dumbbells = self.flat(self.recommend(equipment=['dumbbell']))
        self.assertTrue(any(e['equipment'] == 'dumbbell' for e in with_dumbbells))
        for exercise in with_dumbbells:
            self.assertIn(exercise['equipment'], prototype.NO_EQUIPMENT | {'dumbbell'})

    def test_home_never_gets_gym_exercises(self):
        gym_ids = {e['id'] for e in self.exercises['gym']}
        result = self.recommend(fitness_level='advanced', equipment=sorted(prototype.HOME_EQUIPMENT))
        self.assertFalse(gym_ids & {e['id'] for e in self.flat(result)})

    def test_outdoors_ignores_home_equipment(self):
        for exercise in self.flat(self.recommend(workout_location='outdoors', equipment=['dumbbell'])):
            self.assertIn(exercise['equipment'], prototype.NO_EQUIPMENT)

    def test_gym_and_mixed_can_use_gym_exercises(self):
        gym_ids = {e['id'] for e in self.exercises['gym']}
        for location in ('gym', 'mixed'):
            result = self.recommend(workout_location=location, fitness_level='advanced')
            self.assertTrue(gym_ids & {e['id'] for e in self.flat(result)})

    def test_goal_controls_categories(self):
        for goal, categories in prototype.GOAL_CATEGORIES.items():
            result = self.recommend(fitness_goal=goal, workout_location='gym', fitness_level='advanced')
            self.assertTrue(result, goal)
            for exercise in self.flat(result):
                self.assertIn(exercise['category'], categories)

    def test_every_supabase_value_is_supported(self):
        for goal in prototype.GOAL_CATEGORIES:
            for location in ('home', 'gym', 'outdoors', 'mixed'):
                for level in ('beginner', 'intermediate', 'advanced'):
                    for group in self.recommend(fitness_goal=goal, workout_location=location,
                                                fitness_level=level).values():
                        self.assertLessEqual(len(group), prototype.PER_GROUP)

    def test_profile_from_supabase_row(self):
        row = {'user_id': 'u1', 'name': None, 'age': 42, 'fitness_level': 'beginner', 'fitness_goal': 'lose_weight',
               'workout_location': 'home', 'workout_frequency': 3,
               'user_preferences': {'available_equipment': ['Dumbbell ', 'bands']},
               'user_gamification': None}
        profile = prototype.profile_from_supabase_row(row)
        self.assertEqual(profile['name'], 'u1')
        self.assertEqual(profile['equipment'], ['bands', 'dumbbell'])
        self.assertEqual(profile['points'], 0)
        self.assertEqual(profile['age'], 42)

    def prescribe(self, category, **changes):
        return prototype.prescribe({**self.base, **changes}, {'category': category})

    def test_age_groups(self):
        self.assertEqual(prototype.age_group(13), 'youth')
        self.assertEqual(prototype.age_group(17), 'youth')
        self.assertEqual(prototype.age_group(18), 'adult')
        self.assertEqual(prototype.age_group(64), 'adult')
        self.assertEqual(prototype.age_group(65), 'senior')

    def test_strength_reps_follow_age_and_level(self):
        self.assertEqual(self.prescribe('strength'), '1-3 sets x 8-12 reps')
        self.assertEqual(self.prescribe('strength', fitness_level='advanced'), '3-5 sets x 6-12 reps')
        self.assertEqual(self.prescribe('strength', age=70), '1 set x 10-15 reps')
        self.assertEqual(self.prescribe('strength', age=15), '1-2 sets x 10-15 reps')
        self.assertEqual(self.prescribe('powerlifting', fitness_level='intermediate'), '3 sets x 6-12 reps')

    def test_every_age_level_and_category_has_a_dose(self):
        for age in (13, 30, 80):
            for level in ('beginner', 'intermediate', 'advanced'):
                for category in ('strength', 'powerlifting', 'olympic weightlifting', 'strongman',
                                 'plyometrics', 'stretching', 'cardio'):
                    self.assertTrue(self.prescribe(category, age=age, fitness_level=level))

    def test_stretch_hold_is_longer_for_older_adults(self):
        self.assertEqual(self.prescribe('stretching'), 'hold 10-30 s, 2-4 times')
        self.assertEqual(self.prescribe('stretching', age=65), 'hold 30-60 s, 2-4 times')

    def test_cardio_minutes_split_weekly_guideline_across_days(self):
        self.assertEqual(self.prescribe('cardio'), '50 min moderate effort')  # 150 / 3 days
        self.assertEqual(self.prescribe('cardio', fitness_level='intermediate', workout_frequency=5),
                         '30-60 min moderate effort')
        self.assertEqual(self.prescribe('cardio', fitness_level='advanced', workout_frequency=7),
                         '20-21 min vigorous effort')
        self.assertEqual(self.prescribe('cardio', workout_frequency=1), '60 min moderate effort')  # capped
        self.assertIn('60 min', self.prescribe('cardio', age=14))

    def test_repeatable_and_does_not_change_input(self):
        before = json.dumps(self.base, sort_keys=True)
        self.assertEqual(self.recommend(), self.recommend())
        self.assertEqual(before, json.dumps(self.base, sort_keys=True))


if __name__ == '__main__':
    unittest.main()
