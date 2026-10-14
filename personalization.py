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
        cls.workouts = prototype.load_workout(ROOT / 'Workout.txt')
        cls.catalog = json.loads((ROOT / 'exercise_metadata.json').read_text())
        cls.base = {'fitness_level': 'Beginner', 'goal': 'Building Muscle',
                    'location': 'HOME', 'equipment': []}

    def recommend(self, **changes):
        return prototype.recommend_exercises(
            {**self.base, **changes}, self.workouts, self.catalog)

    @staticmethod
    def names(result):
        return {exercise['name'] for group in result.values() for exercise in group}

    def test_level_changes_exercises(self):
        beginner = self.names(self.recommend())
        intermediate = self.names(self.recommend(fitness_level='Intermediate'))
        self.assertNotEqual(beginner, intermediate)
        self.assertNotIn('pushups', beginner)
        self.assertIn('pushups', intermediate)

    def test_goal_changes_exercises_and_displays_full_body(self):
        endurance = self.recommend(goal='Improve Endurance')
        self.assertIn('Full Body', endurance)
        self.assertEqual(self.names(endurance), {'mountain climbers'})
        self.assertNotEqual(self.names(self.recommend()), self.names(endurance))

    def test_equipment_changes_exercises(self):
        self.assertNotIn('dumbbell bicep curl', self.names(self.recommend()))
        self.assertIn('dumbbell bicep curl', self.names(self.recommend(equipment=['dumbbells'])))

    def test_general_fitness_includes_core(self):
        self.assertIn('Core', self.recommend(goal='General Body Fitness'))

    def test_every_catalog_exercise_has_metadata(self):
        for locations in self.workouts.values():
            for categories in locations.values():
                for exercises in categories.values():
                    for exercise in exercises:
                        self.assertIn(exercise['name'], self.catalog)

    def test_constraints_for_every_goal_location_and_level(self):
        for goal, locations in self.workouts.items():
            for location in locations:
                for level in prototype.LEVEL_RANK:
                    for equipment in ([], ['dumbbells'], sorted(prototype.EQUIPMENT_CHOICES)):
                        result = self.recommend(goal=goal, location=location,
                                                fitness_level=level, equipment=equipment)
                        for exercises in result.values():
                            self.assertLessEqual(len(exercises), 3)
                            for exercise in exercises:
                                self.assertTrue(set(exercise['required_equipment']) <= set(equipment))
                                self.assertLessEqual(prototype.LEVEL_RANK[exercise['minimum_level']],
                                                     prototype.LEVEL_RANK[level])

    def test_unknown_equipment_is_rejected(self):
        with self.assertRaises(ValueError):
            self.recommend(equipment=['unknown'])
        with self.assertRaises(ValueError):
            self.recommend(equipment='none, dumbbells')

    def test_repeatable_and_does_not_change_input(self):
        before = json.dumps(self.base, sort_keys=True)
        self.assertEqual(self.recommend(), self.recommend())
        self.assertEqual(before, json.dumps(self.base, sort_keys=True))


if __name__ == '__main__':
    unittest.main()
