import importlib.util
import json
from pathlib import Path
from datetime import date, timedelta
import tempfile
import unittest

import numpy as np

import exercise_ranker as ranker
import progress_forecast as forecast
import seed_week_one as seed
import weight_forecast_model as wfm
import weekly_plan as plans
from app import healthscore as hs  # progress_forecast puts backend/ on the path

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

    def dose(self, category, **changes):
        profile = {**self.base, **changes}
        return prototype.dose_range(profile, {'category': category}, profile['workout_frequency'])

    def test_age_groups(self):
        self.assertEqual(prototype.age_group(13), 'youth')
        self.assertEqual(prototype.age_group(17), 'youth')
        self.assertEqual(prototype.age_group(18), 'adult')
        self.assertEqual(prototype.age_group(64), 'adult')
        self.assertEqual(prototype.age_group(65), 'senior')

    def test_strength_reps_follow_age_and_level(self):
        self.assertEqual(self.dose('strength'), {'sets': (1, 3), 'reps': (8, 12), 'minutes': None})
        self.assertEqual(self.dose('strength', fitness_level='advanced')['sets'], (3, 5))
        self.assertEqual(self.dose('strength', age=70)['reps'], (10, 15))
        self.assertEqual(self.dose('strength', age=15)['sets'], (1, 2))
        self.assertEqual(self.dose('powerlifting', fitness_level='intermediate')['sets'], (3, 3))
        self.assertEqual(self.dose('plyometrics')['reps'], (5, 8))

    def test_every_age_level_and_category_has_a_dose(self):
        for age in (13, 30, 80):
            for level in ('beginner', 'intermediate', 'advanced'):
                for category in ('strength', 'powerlifting', 'olympic weightlifting', 'strongman',
                                 'plyometrics', 'stretching', 'cardio'):
                    dose = self.dose(category, age=age, fitness_level=level)
                    for low, high in filter(None, dose.values()):
                        self.assertTrue(0 < low <= high)

    def test_stretching_is_2_to_4_holds(self):
        self.assertEqual(self.dose('stretching'), {'sets': (2, 4), 'reps': None, 'minutes': None})

    def test_cardio_minutes_split_weekly_guideline_across_days(self):
        self.assertEqual(self.dose('cardio')['minutes'], (50, 50))  # 150 / 3 days
        self.assertEqual(self.dose('cardio', fitness_level='intermediate', workout_frequency=5)['minutes'], (30, 60))
        self.assertEqual(self.dose('cardio', fitness_level='advanced', workout_frequency=7)['minutes'], (20, 21))
        self.assertEqual(self.dose('cardio', workout_frequency=1)['minutes'], (60, 60))  # capped
        self.assertEqual(self.dose('cardio', age=14)['minutes'], (60, 60))

    def test_repeatable_and_does_not_change_input(self):
        before = json.dumps(self.base, sort_keys=True)
        self.assertEqual(self.recommend(), self.recommend())
        self.assertEqual(before, json.dumps(self.base, sort_keys=True))


class FakeTable:
    """Pages like Supabase: range() is inclusive and no response has more than max_rows."""

    def __init__(self, rows, max_rows=1000):
        self.source, self.rows, self.max_rows, self.start, self.end = rows, rows, max_rows, 0, len(rows) - 1

    def select(self, *args, **kwargs):
        return self

    def eq(self, column, value):
        self.rows = [row for row in self.rows if row.get(column) == value]
        return self

    def insert(self, rows):
        self.source.extend(rows)
        self.rows = rows
        return self

    def order(self, key):
        self.rows = sorted(self.rows, key=lambda row: row[key])
        return self

    def range(self, start, end):
        self.start, self.end = start, end
        return self

    def execute(self):
        self.data = self.rows[self.start:self.end + 1][:self.max_rows]
        return self


class FakeClient:
    def __init__(self, tables, max_rows=1000):
        self.tables, self.max_rows = tables, max_rows

    def table(self, name):
        return FakeTable(self.tables[name], self.max_rows)


class RankerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exercises = prototype.load_exercises()
        cls.base = {'age': 30, 'fitness_level': 'advanced', 'fitness_goal': 'build_muscle',
                    'workout_location': 'gym', 'workout_frequency': 3, 'equipment': [],
                    'workout_preferences': ['strength']}
        # Synthetic history: this user only ever finishes isolation exercises.
        pool = cls.exercises['gym'][:150]
        cls.rows = [(cls.base, e, int(e['mechanic'] == 'isolation')) for e in pool]
        cls.model = ranker.train(cls.rows)

    def test_features_match_names(self):
        row = ranker.features(self.base, self.exercises['home'][0])
        self.assertEqual(len(row), len(ranker.FEATURE_NAMES))

    def test_model_learns_from_history(self):
        isolation = [e for e in self.exercises['gym'] if e['mechanic'] == 'isolation'][:5]
        compound = [e for e in self.exercises['gym'] if e['mechanic'] == 'compound'][:5]
        iso_scores = ranker.scores(self.model, self.base, isolation)
        comp_scores = ranker.scores(self.model, self.base, compound)
        self.assertGreater(min(iso_scores), max(comp_scores))

    def test_model_reorders_but_keeps_rules(self):
        rules = prototype.recommend_exercises(self.base, self.exercises)
        ranked = prototype.recommend_exercises(self.base, self.exercises, self.model)
        self.assertNotEqual(rules, ranked)
        allowed = {e['id'] for e in prototype.candidate_exercises(self.base, self.exercises)}
        for group, exercises in ranked.items():
            self.assertLessEqual(len(exercises), prototype.PER_GROUP)
            for exercise in exercises:
                self.assertIn(exercise['id'], allowed)
                self.assertIn(exercise['category'], prototype.GOAL_CATEGORIES['build_muscle'])
                self.assertEqual(prototype.muscle_group(exercise), group)

    def test_isolation_ranked_first_when_user_prefers_it(self):
        ranked = prototype.recommend_exercises(self.base, self.exercises, self.model)
        self.assertEqual(ranked['Upper Body'][0]['mechanic'], 'isolation')

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'model.json'
            self.assertIsNone(ranker.load_model(path))
            ranker.save_model(self.model, path)
            loaded = ranker.load_model(path)
            exercises = self.exercises['gym'][:10]
            for a, b in zip(ranker.scores(self.model, self.base, exercises),
                            ranker.scores(loaded, self.base, exercises)):
                self.assertAlmostEqual(a, b, places=5)

    def test_training_needs_both_outcomes(self):
        with self.assertRaises(ValueError):
            ranker.train([(self.base, e, 1) for e in self.exercises['gym'][:20]])

    def test_training_rows_from_supabase(self):
        squat, curl = self.exercises['gym'][0], self.exercises['gym'][1]
        client = FakeClient({
            'profiles': [{'user_id': 'u1', 'age': 25, 'fitness_level': 'beginner',
                          'fitness_goal': 'build_muscle', 'workout_location': 'gym',
                          'workout_frequency': 3, 'workout_preferences': ['cardio']}],
            'workout_logs': [{'workout_log_id': 'l1', 'plan_id': 'p1', 'completion_status': 'skipped'},
                             {'workout_log_id': 'l2', 'plan_id': 'p1', 'completion_status': 'completed'},
                             {'workout_log_id': 'l3', 'plan_id': 'p2', 'completion_status': 'skipped'},
                             {'workout_log_id': 'l4', 'plan_id': None, 'completion_status': 'completed'}],
            'plan_exercises': [
                {'plan_exercise_id': 'e1', 'plan_id': 'p1', 'workout_plans': {'user_id': 'u1'},
                 'exercises': {'name': squat['name'].upper()}},
                {'plan_exercise_id': 'e2', 'plan_id': 'p2', 'workout_plans': {'user_id': 'u1'},
                 'exercises': {'name': curl['name']}},
                {'plan_exercise_id': 'e3', 'plan_id': 'p3', 'workout_plans': {'user_id': 'u1'},
                 'exercises': {'name': curl['name']}},  # no log
                {'plan_exercise_id': 'e4', 'plan_id': 'p1', 'workout_plans': {'user_id': 'u1'},
                 'exercises': {'name': 'Not In JSON'}},
            ],
        })
        rows = ranker.training_rows_from_supabase(client, prototype.profile_from_supabase_row, self.exercises)
        self.assertEqual([(e['id'], label) for _, e, label in rows], [(squat['id'], 1), (curl['id'], 0)])
        self.assertEqual(rows[0][0]['workout_preferences'], ['cardio'])

    def test_fetch_all_reads_past_the_row_limit(self):
        rows = [{'id': f'{i:05d}'} for i in range(2500)]
        self.assertEqual(ranker.fetch_all(FakeClient({'t': rows}), 't', '*', 'id'), rows)
        # A project whose max-rows setting is below PAGE_SIZE still gets every row.
        self.assertEqual(ranker.fetch_all(FakeClient({'t': rows}, max_rows=300), 't', '*', 'id'), rows)
        self.assertEqual(ranker.fetch_all(FakeClient({'t': []}), 't', '*', 'id'), [])

    def test_training_reads_every_plan_exercise(self):
        exercise = self.exercises['gym'][0]
        client = FakeClient({
            'profiles': [{'user_id': 'u1', 'age': 25, 'fitness_level': 'beginner',
                          'fitness_goal': 'build_muscle', 'workout_location': 'gym', 'workout_frequency': 3}],
            'workout_logs': [{'workout_log_id': 'l1', 'plan_id': 'p1', 'completion_status': 'completed'}],
            'plan_exercises': [{'plan_exercise_id': f'{i:05d}', 'plan_id': 'p1', 'workout_plans': {'user_id': 'u1'},
                                'exercises': {'name': exercise['name']}} for i in range(1500)],
        })
        rows = ranker.training_rows_from_supabase(client, prototype.profile_from_supabase_row, self.exercises)
        self.assertEqual(len(rows), 1500)


TODAY = date(2026, 10, 23)  # a Friday; the last complete week starts Monday 2026-10-12
LAST_MONDAY = date(2026, 10, 12)


def weeks_ago(n, weekday=2):
    """A date n weeks before the last complete week (Wednesday by default)."""
    return (LAST_MONDAY - timedelta(weeks=n, days=-weekday)).isoformat()


class ForecastTests(unittest.TestCase):
    def profile(self, **changes):
        return {'user_id': 'u1', 'created_at': weeks_ago(11) + 'T08:00:00+00:00', 'weight_kg': 80.0,
                'fitness_goal': 'lose_weight', 'fitness_level': 'beginner', 'workout_frequency': 3,
                **changes}

    def history(self, weights=(), workouts_per_week=None, weeks=12, steps=()):
        """weights/steps are [(weeks ago, value)]; workouts_per_week fills every week."""
        logs = []
        if workouts_per_week is not None:
            logs = [{'workout_date': weeks_ago(n, day), 'completion_status': 'completed'}
                    for n in range(weeks) for day in range(workouts_per_week)]
        return {
            'body_measurements': [{'recorded_at': weeks_ago(n) + 'T07:00:00+00:00', 'weight_kg': w}
                                  for n, w in weights],
            'workout_logs': logs,
            'activity_logs': [{'log_date': weeks_ago(n), 'steps': v} for n, v in steps],
        }

    def test_fit_recovers_a_clear_trend(self):
        points = [(-n, 90 - 0.4 * (11 - n)) for n in range(12)]
        level, slope = forecast.fit_trend(points, 0.0)
        self.assertAlmostEqual(slope, -0.4, delta=0.05)
        self.assertAlmostEqual(level, 90 - 0.4 * 11, delta=0.3)

    def test_single_week_follows_the_prior(self):
        level, slope = forecast.fit_trend([(0, 75.0)], -0.5)
        self.assertAlmostEqual(level, 75.0)
        self.assertAlmostEqual(slope, -0.5)

    def test_new_user_forecast_comes_from_profile(self):
        profile = self.profile(created_at=TODAY.isoformat())
        result = forecast.forecast_user(profile, self.history(), TODAY)
        self.assertEqual(result['workouts_per_week']['level'], 3)
        weight = result['weight_kg']
        self.assertAlmostEqual(weight['slope'], -forecast.WEIGHT_LOSS_PER_WEEK)
        self.assertAlmostEqual(weight['predictions'][0][1], 79.5)
        self.assertNotIn('daily_steps', result)
        self.assertNotIn('health_score', result)

    def test_goal_sets_weight_direction(self):
        history = self.history(weights=[(0, 70.0)], workouts_per_week=3)
        gain = forecast.forecast_user(self.profile(fitness_goal='build_muscle'), history, TODAY)['weight_kg']
        flat = forecast.forecast_user(self.profile(fitness_goal='general_fitness'), history, TODAY)['weight_kg']
        self.assertAlmostEqual(gain['slope'], 70 * 0.01 / forecast.WEEKS_PER_MONTH, places=3)
        self.assertAlmostEqual(flat['slope'], 0.0)
        advanced = forecast.forecast_user(self.profile(fitness_goal='build_muscle', fitness_level='advanced'),
                                          history, TODAY)['weight_kg']
        self.assertLess(advanced['slope'], gain['slope'])

    def test_missed_workouts_shrink_expected_weight_change(self):
        weights = [(0, 80.0)]
        full = forecast.forecast_user(self.profile(), self.history(weights, workouts_per_week=3), TODAY)
        partial = forecast.forecast_user(self.profile(), self.history(weights, workouts_per_week=1), TODAY)
        none = forecast.forecast_user(self.profile(), self.history(weights, workouts_per_week=0), TODAY)
        self.assertAlmostEqual(full['workouts_per_week']['level'], 3, places=5)
        self.assertAlmostEqual(full['weight_kg']['adherence'], 1.0, places=5)
        self.assertAlmostEqual(partial['weight_kg']['adherence'], 1 / 3, places=5)
        self.assertAlmostEqual(none['weight_kg']['slope'], 0.0)
        self.assertLess(full['weight_kg']['slope'], partial['weight_kg']['slope'])

    def test_adapts_as_weeks_of_data_arrive(self):
        # The goal says lose weight, but this user gains 0.3 kg every week.
        def slope_after(weeks):
            weights = [(n, 80 + 0.3 * (weeks - 1 - n)) for n in range(weeks)]
            result = forecast.forecast_user(self.profile(), self.history(weights, workouts_per_week=3), TODAY)
            return result['weight_kg']['slope']
        slopes = [slope_after(w) for w in (1, 2, 4, 8, 12)]
        self.assertAlmostEqual(slopes[0], -0.5)
        self.assertEqual(slopes, sorted(slopes))  # moves steadily toward the user's real trend
        self.assertGreater(slopes[-1], 0.2)

    def test_recent_weeks_count_more(self):
        old_habit = [(n, 4) for n in range(4, 12)]
        recent = forecast.fit_trend([(-n, v) for n, v in old_habit] + [(-n, 1) for n in range(4)], 0.0)
        level = recent[0]
        self.assertLess(level, 2.5)

    def test_current_partial_week_is_ignored(self):
        history = self.history(weights=[(0, 80.0)], workouts_per_week=3)
        history['body_measurements'].append({'recorded_at': TODAY.isoformat(), 'weight_kg': 120.0})
        history['workout_logs'] += [{'workout_date': TODAY.isoformat(), 'completion_status': 'completed'}] * 5
        result = forecast.forecast_user(self.profile(), history, TODAY)
        self.assertEqual(result['weight_kg']['weeks_of_data'], 1)
        self.assertAlmostEqual(result['workouts_per_week']['level'], 3, places=5)

    def test_skipped_workouts_do_not_count(self):
        history = self.history(workouts_per_week=0)
        history['workout_logs'] = [{'workout_date': weeks_ago(n), 'completion_status': 'skipped'} for n in range(12)]
        result = forecast.forecast_user(self.profile(), history, TODAY)
        self.assertAlmostEqual(result['workouts_per_week']['level'], 0.0)

    def test_steps(self):
        history = self.history(steps=[(n, 6000 + 250 * (11 - n)) for n in range(12)])
        result = forecast.forecast_user(self.profile(), history, TODAY)
        self.assertGreater(result['daily_steps']['slope'], 200)

    def health_weeks(self, weeks=8, **trends):
        """Weekly backend results; trends maps category -> (score now, change per week) or None."""
        results = []
        for n in reversed(range(weeks)):
            scores = {c: None for c in hs.CATEGORIES}
            for category, trend in trends.items():
                if trend is not None:
                    scores[category] = trend[0] - trend[1] * n
            results.append((LAST_MONDAY - timedelta(weeks=n), hs.build_result(
                {c: hs.CategoryResult(scores[c], {}) for c in hs.CATEGORIES})))
        return results

    def test_health_score_matches_the_backend_weights(self):
        weeks = self.health_weeks(workouts=(60, 2), nutrition=(80, 0), sleep=(90, -1), activity=(70, 1))
        result = forecast.forecast_health(weeks, hs.DEFAULT_WEIGHTS, LAST_MONDAY)
        self.assertEqual(result['missing'], [])
        # Every point is the backend's weighted overall score of the category forecasts.
        for i, (_, value) in enumerate(result['predictions']):
            parts = {c: f['predictions'][i][1] for c, f in result['categories'].items()}
            self.assertAlmostEqual(value, hs.overall_score(parts, hs.DEFAULT_WEIGHTS))
        self.assertGreater(result['categories']['workouts']['slope'], 1)
        self.assertLess(result['categories']['sleep']['slope'], 0)
        self.assertEqual(result['history'][-1][1], hs.build_result(
            {c: hs.CategoryResult(v, {}) for c, v in
             {'workouts': 60, 'nutrition': 80, 'sleep': 90, 'activity': 70}.items()})['overall_score'])

    def test_health_score_weights_come_from_config(self):
        weeks = self.health_weeks(workouts=(40, 0), sleep=(100, 0))
        sleep_heavy = {'workouts': 0.1, 'nutrition': 0.3, 'sleep': 0.5, 'activity': 0.1}
        default = forecast.forecast_health(weeks, hs.DEFAULT_WEIGHTS, LAST_MONDAY)
        custom = forecast.forecast_health(weeks, sleep_heavy, LAST_MONDAY)
        self.assertGreater(custom['level'], default['level'])

    def test_health_score_is_provisional_with_missing_categories(self):
        weeks = self.health_weeks(sleep=(85, 0), activity=(65, 0))
        result = forecast.forecast_health(weeks, hs.DEFAULT_WEIGHTS, LAST_MONDAY)
        self.assertEqual(result['missing'], ['workouts', 'nutrition'])
        # Like the screen's provisional score: re-weighted over sleep (0.25) and activity (0.20).
        self.assertAlmostEqual(result['level'], (0.25 * 85 + 0.20 * 65) / 0.45, places=3)
        self.assertIsNone(forecast.forecast_health(self.health_weeks(), hs.DEFAULT_WEIGHTS, LAST_MONDAY))

    def test_health_score_stays_in_range(self):
        weeks = self.health_weeks(workouts=(95, 5), nutrition=(10, -5))
        result = forecast.forecast_health(weeks, hs.DEFAULT_WEIGHTS, LAST_MONDAY)
        self.assertEqual(result['categories']['workouts']['predictions'][-1][1], 100.0)
        self.assertEqual(result['categories']['nutrition']['predictions'][-1][1], 0.0)

    def test_health_score_in_user_forecast_and_rows(self):
        health = {'weeks': self.health_weeks(workouts=(75, 0), sleep=(90, 0)), 'weights': hs.DEFAULT_WEIGHTS}
        result = forecast.forecast_user(self.profile(), self.history(), TODAY, health=health)
        rows = forecast.forecast_rows('u1', result)
        types = {r['prediction_type'] for r in rows}
        self.assertTrue({'health_score', 'health_score_workouts', 'health_score_sleep'} <= types)
        self.assertNotIn('health_score_nutrition', types)
        self.assertIn('  Sleep: 90 now -> 90 in 12 wk (weight 25%)', forecast.format_forecast(result))

    def test_planned_workout_days_override_onboarding(self):
        history = self.history(weights=[(0, 80.0)], workouts_per_week=3)
        result = forecast.forecast_user(self.profile(), history, TODAY, workout_days=6)
        self.assertAlmostEqual(result['weight_kg']['adherence'], 0.5, places=5)
        new_user = forecast.forecast_user(self.profile(created_at=TODAY.isoformat()), self.history(), TODAY,
                                          workout_days=5)
        self.assertEqual(new_user['workouts_per_week']['level'], 5)

    def test_weight_change_is_capped(self):
        weights = [(n, 100 - 3 * (5 - n)) for n in range(6)]
        result = forecast.forecast_user(self.profile(), self.history(weights, workouts_per_week=3), TODAY)
        self.assertEqual(result['weight_kg']['slope'], -forecast.MAX_WEEKLY_WEIGHT_CHANGE)

    def test_prediction_dates_are_week_ends(self):
        result = forecast.forecast_user(self.profile(), self.history(), TODAY)
        dates = [target for target, _ in result['weight_kg']['predictions']]
        self.assertEqual(dates, [date(2026, 10, 25), date(2026, 11, 15), date(2027, 1, 10)])
        self.assertTrue(all(d.weekday() == 6 for d in dates))

    def supabase(self):
        return FakeClient({
            'profiles': [self.profile(), self.profile(user_id='u2', weight_kg=None)],
            'body_measurements': [{'measurement_id': 'm1', 'user_id': 'u1', 'recorded_at': weeks_ago(1), 'weight_kg': 79.0}],
            'workout_logs': [{'workout_log_id': 'w1', 'user_id': 'u2', 'workout_date': weeks_ago(0),
                              'completion_status': 'completed'}],
            'activity_logs': [], 'progress_forecasts': [],
        })

    @staticmethod
    def no_health(client, profile, history, today):
        return {'workout_days': None, 'health': None}

    def test_forecast_from_supabase_reads_only_that_user(self):
        result = forecast.forecast_from_supabase(self.supabase(), 'u2', TODAY, self.no_health)
        self.assertNotIn('weight_kg', result)  # u2 has no weight and no measurements
        self.assertEqual(result['workouts_per_week']['weeks_of_data'], 12)
        with self.assertRaises(LookupError):
            forecast.forecast_from_supabase(self.supabase(), 'nobody', TODAY, self.no_health)

    def test_weekly_run_saves_once_per_week(self):
        client = self.supabase()
        rows = forecast.run_weekly(client, TODAY, context=self.no_health)
        saved = client.tables['progress_forecasts']
        self.assertEqual(len(saved), len(rows))
        # u1: 4 metrics minus steps and HealthScore; u2: workouts only.
        self.assertEqual(len(rows), 3 * len(forecast.HORIZONS))
        self.assertEqual({r['prediction_type'] for r in rows if r['user_id'] == 'u1'},
                         {'weight_kg', 'workouts_per_week'})
        for row in saved:
            row.update(forecast_id=str(id(row)), generated_at=TODAY.isoformat() + 'T06:00:00+00:00')
        self.assertEqual(forecast.run_weekly(client, TODAY, context=self.no_health), [])
        # Next week everyone is forecast again with that week's data.
        self.assertEqual(len(forecast.run_weekly(client, TODAY + timedelta(days=7), context=self.no_health)), len(rows))

    def test_dry_run_saves_nothing(self):
        client = self.supabase()
        self.assertTrue(forecast.run_weekly(client, TODAY, dry_run=True, context=self.no_health))
        self.assertEqual(client.tables['progress_forecasts'], [])

    def test_chart_lines_join_logged_weeks_to_the_forecast(self):
        history = self.history(weights=[(1, 81.0), (0, 80.0)], workouts_per_week=3)
        logged, future = forecast.chart_lines(forecast.forecast_user(self.profile(), history, TODAY)['weight_kg'])
        self.assertEqual(logged, [(date(2026, 10, 5), 81.0), (date(2026, 10, 12), 80.0)])
        # The dashed line starts at the last logged week, then each forecast week's Monday.
        self.assertEqual([d for d, _ in future],
                         [date(2026, 10, 12), date(2026, 10, 19), date(2026, 11, 9), date(2027, 1, 4)])
        new_user = forecast.forecast_user(self.profile(created_at=TODAY.isoformat()), self.history(), TODAY)
        logged, future = forecast.chart_lines(new_user['workouts_per_week'])
        self.assertEqual(logged, [])
        self.assertEqual(future[0], (LAST_MONDAY, 3.0))  # from the fitted level

    def test_flat_line_gets_a_visible_axis(self):
        lo, hi = forecast.y_limits('weight_kg', [68.5, 68.50000000000001])
        self.assertGreater(hi - lo, 1)
        self.assertEqual(forecast.y_limits('health_score', [90, 100])[1], 100.0)
        lo, hi = forecast.y_limits('daily_steps', [0, 0])
        self.assertTrue(-0.1 < lo < 0 < hi)  # zero stays above the bottom edge

    def test_write_chart_saves_a_png(self):
        health = {'weeks': self.health_weeks(workouts=(50, 5), sleep=(90, 0)), 'weights': hs.DEFAULT_WEIGHTS}
        full = forecast.forecast_user(self.profile(), self.history([(1, 81.0), (0, 80.0)], workouts_per_week=3,
                                                                    steps=[(0, 7000)]), TODAY, health=health)
        empty = forecast.forecast_user(self.profile(weight_kg=None, created_at=TODAY.isoformat()),
                                       self.history(), TODAY)
        with tempfile.TemporaryDirectory() as folder:
            for user_id, result in [('full', full), ('empty', empty)]:
                path = forecast.write_chart(user_id, result, 'Sam', folder)
                self.assertEqual(path, Path(folder) / f'forecast-{user_id}.png')
                self.assertEqual(path.read_bytes()[:8], b'\x89PNG\r\n\x1a\n')

    def test_format_forecast(self):
        text = forecast.format_forecast(forecast.forecast_user(self.profile(), self.history(), TODAY))
        self.assertIn('Weight: 80.0 kg now', text)
        self.assertIn('HealthScore: no data yet', text)


class WeightModelTests(unittest.TestCase):
    """The XGBoost correction on top of the linear baseline (weight_forecast_model.py)."""

    @classmethod
    def setUpClass(cls):
        cls.grouped = wfm.synthetic_rows(n_users=40, seed=1)
        train_rows, validation_rows = wfm.split_by_user(cls.grouped)
        cls.model = wfm.train(train_rows, validation_rows)
        cls.validation = validation_rows

    def profile(self, **changes):
        return {'user_id': 'u1', 'created_at': weeks_ago(11) + 'T08:00:00+00:00', 'weight_kg': 80.0, 'age': 30,
                'fitness_goal': 'lose_weight', 'fitness_level': 'beginner', 'workout_frequency': 3, **changes}

    def history(self, weights):
        return {'body_measurements': [{'recorded_at': weeks_ago(n) + 'T07:00:00+00:00', 'weight_kg': w}
                                      for n, w in weights],
                'workout_logs': [{'workout_date': weeks_ago(n, day), 'completion_status': 'completed'}
                                 for n in range(12) for day in range(3)],
                'activity_logs': []}

    def test_feature_rows_match_the_feature_names(self):
        rows = [row for _, rows in self.grouped for row in rows]
        self.assertGreater(len(rows), 300)
        self.assertTrue(all(len(features) == len(wfm.FEATURE_NAMES) for features, *_ in rows))

    def test_features_only_use_data_the_baseline_had(self):
        profile, history = wfm.synthetic_user(np.random.default_rng(3), date(2026, 10, 19), 'sim')
        today = date(2026, 8, 17)  # the forecast may only see weeks that ended before this Monday
        origin = forecast.last_complete_week(today)

        def features(hist):
            result = forecast.forecast_user(profile, hist, today, use_ml=False)
            return wfm.user_features(profile, result, origin)

        future = {table: [{**row, **({'weight_kg': row['weight_kg'] + 50} if 'weight_kg' in row else {'steps': 99999})}
                          if pf_date(next(v for k, v in row.items() if k.endswith(('_at', '_date')))) >= today else row
                          for row in rows]
                  for table, rows in history.items()}
        self.assertNotEqual(future['body_measurements'], history['body_measurements'])
        self.assertEqual(features(history), features(future))

    def test_model_beats_the_baseline_on_held_out_users(self):
        report = wfm.evaluate(self.model, self.validation)
        self.assertEqual(set(report), set(forecast.HORIZONS))
        base, ml, _ = report[12]
        self.assertLess(ml, base)

    def test_apply_corrects_and_keeps_the_baseline(self):
        history = self.history([(n, 80 + 0.3 * n) for n in range(8)])
        plain = forecast.forecast_user(self.profile(), history, TODAY, use_ml=False)
        result = forecast.forecast_user(self.profile(), history, TODAY, weight_model=self.model)
        weight = result['weight_kg']
        self.assertEqual(weight['baseline_predictions'], plain['weight_kg']['predictions'])
        self.assertEqual(weight['model_version'], forecast.ML_MODEL_VERSION)
        self.assertEqual(len(weight['ml_corrections']), len(forecast.HORIZONS))
        for h, fix in zip(forecast.HORIZONS, weight['ml_corrections']):
            self.assertLessEqual(abs(fix), max(1.0, wfm.MAX_CORRECTION_KG_PER_WEEK * h))
        self.assertIn('XGBoost', forecast.format_forecast(result))
        self.assertNotIn('model_version', plain['weight_kg'])
        rows = forecast.forecast_rows('u1', result)
        self.assertEqual({r['model_version'] for r in rows if r['prediction_type'] == 'weight_kg'},
                         {forecast.ML_MODEL_VERSION})
        self.assertEqual({r['model_version'] for r in rows if r['prediction_type'] != 'weight_kg'},
                         {forecast.MODEL_VERSION})

    def test_new_users_keep_the_plain_baseline(self):
        profile = self.profile(created_at=TODAY.isoformat())
        result = forecast.forecast_user(profile, self.history([]), TODAY, weight_model=self.model)
        self.assertNotIn('baseline_predictions', result['weight_kg'])
        self.assertAlmostEqual(result['weight_kg']['predictions'][0][1], 79.5)

    def test_no_saved_model_means_baseline_only(self):
        history = self.history([(n, 80 + 0.3 * n) for n in range(8)])
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(wfm.load_model(Path(folder) / 'missing.json'))

    def test_model_survives_save_and_load(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'models' / 'weight_forecast.json'
            wfm.save_model(self.model, path)
            loaded = wfm.load_model(path)
        shared = wfm.user_features(self.profile(), forecast.forecast_user(
            self.profile(), self.history([(n, 80 + 0.3 * n) for n in range(8)]), TODAY, use_ml=False),
            forecast.last_complete_week(TODAY))
        self.assertEqual(wfm.corrections(self.model, shared), wfm.corrections(loaded, shared))


def pf_date(value):
    return date.fromisoformat(str(value)[:10])


class WeeklyPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exercises = prototype.load_exercises()
        cls.profile = {'user_id': 'u1', 'name': 'Sam', 'age': 30, 'fitness_level': 'beginner',
                       'fitness_goal': 'general_fitness', 'workout_location': 'home', 'workout_frequency': 3,
                       'equipment': [], 'workout_preferences': [], 'points': 0}
        cls.week_one = plans.first_week(cls.profile, cls.exercises, date(2026, 10, 5))

    @staticmethod
    def logs(*statuses):
        return [{'day_number': day, 'completion_status': s} for day, s in enumerate(statuses, 1) if s]

    @staticmethod
    def by_day(plan, day):
        return {item['group']: item for item in plan['items'] if item['day'] == day}

    def test_first_week_spreads_groups_over_days_at_the_bottom_of_the_range(self):
        self.assertEqual(self.week_one['days'], 3)
        groups = set(prototype.recommend_exercises(self.profile, self.exercises))
        for day in (1, 2, 3):
            self.assertEqual(set(self.by_day(self.week_one, day)), groups)
        self.assertNotEqual(self.by_day(self.week_one, 1)['Core']['exercise']['id'],
                            self.by_day(self.week_one, 2)['Core']['exercise']['id'])
        core = self.by_day(self.week_one, 1)['Core']
        self.assertEqual((core['sets'], core['reps']), (1, 8))  # adult beginner: 1-3 sets x 8-12 reps
        cardio = self.by_day(self.week_one, 1)['Cardio']
        self.assertEqual(cardio['minutes'], 50)  # 150 weekly minutes over 3 days
        self.assertIsNone(cardio['sets'])

    def test_full_week_progresses(self):
        week_two = plans.next_week(self.profile, self.exercises, self.week_one, self.logs(*['completed'] * 3))
        self.assertEqual(week_two['week_start'], date(2026, 10, 12))
        self.assertEqual(week_two['days'], 3)
        for day in (1, 2, 3):
            before, after = self.by_day(self.week_one, day), self.by_day(week_two, day)
            self.assertEqual(after['Core']['exercise']['id'], before['Core']['exercise']['id'])
            self.assertEqual(after['Core']['reps'], 10)
            self.assertEqual(after['Cardio']['minutes'], 50)  # already at the beginner cap

    def test_skipped_day_swaps_its_exercises_and_keeps_the_rest(self):
        week_two = plans.next_week(self.profile, self.exercises, self.week_one,
                                   self.logs('completed', 'completed', 'skipped'))
        self.assertEqual(week_two['days'], 3)  # 2/3 done: same dose
        self.assertEqual(self.by_day(week_two, 1)['Core'], self.by_day(self.week_one, 1)['Core'])
        swapped = self.by_day(week_two, 3)['Core']['exercise']['id']
        self.assertNotIn(swapped, {item['exercise']['id'] for item in self.week_one['items']})

    def test_low_completion_cuts_days_and_volume(self):
        busy = {**self.profile, 'workout_frequency': 5}
        week_one = plans.first_week(busy, self.exercises, date(2026, 10, 5))
        for item in week_one['items']:
            if item['reps']:
                item['sets'], item['reps'] = 3, 12
        week_two = plans.next_week(busy, self.exercises, week_one, self.logs('completed', 'partial'))
        self.assertEqual(week_two['days'], 3)  # did 2 of 5 days: plan one more than that
        core = self.by_day(week_two, 1)['Core']
        self.assertEqual((core['sets'], core['reps']), (2, 12))  # one set down

    def test_steps_stay_inside_the_range(self):
        bounds = {'sets': (1, 3), 'reps': (8, 12), 'minutes': None}
        self.assertEqual(plans.step_up({'sets': 1, 'reps': 12, 'minutes': None}, bounds)['sets'], 2)
        self.assertEqual(plans.step_up({'sets': 1, 'reps': 12, 'minutes': None}, bounds)['reps'], 8)
        self.assertEqual(plans.step_up({'sets': 3, 'reps': 12, 'minutes': None}, bounds),
                         {'sets': 3, 'reps': 12, 'minutes': None})
        self.assertEqual(plans.step_down({'sets': 1, 'reps': 8, 'minutes': None}, bounds),
                         {'sets': 1, 'reps': 8, 'minutes': None})

    def test_unlogged_days_count_as_skipped(self):
        self.assertAlmostEqual(plans.completion_rate(self.week_one, self.logs('completed', 'partial')), 0.5)

    def test_format_plan(self):
        text = plans.format_plan(self.profile, self.week_one)
        self.assertIn('WEEK OF 2026-10-05', text)
        self.assertIn('--- Day 3 ---', text)
        self.assertIn('1 set x 8 reps', text)
        self.assertIn('50 min moderate effort', text)
        self.assertIn('hold 10-30 s, 2 times', text)
        self.assertIn('hold 30-60 s', plans.format_plan({**self.profile, 'age': 70}, self.week_one))
        youth = {**self.profile, 'age': 15}
        self.assertIn('60 min moderate-to-vigorous effort',
                      plans.format_plan(youth, plans.first_week(youth, self.exercises, date(2026, 10, 5))))

    def test_exercise_rows_fit_the_table_constraints(self):
        rows = [plans.exercise_row(e) for e in self.exercises['home'] + self.exercises['gym']]
        self.assertLessEqual({r['workout_type'] for r in rows}, set(ranker.PREFERENCES))
        self.assertLessEqual({r['difficulty'] for r in rows}, {'beginner', 'intermediate', 'advanced'})

    def test_seed_links_week_one_logs_only(self):
        row = {'user_id': 'u1', 'created_at': '2026-10-23T18:52:00+00:00', 'name': 'Sam', 'age': 30,
               'fitness_level': 'beginner', 'fitness_goal': 'general_fitness', 'workout_location': 'home',
               'workout_frequency': 3, 'workout_preferences': [], 'user_preferences': None,
               'user_gamification': None}
        profiles = [row, {**row, 'user_id': 'u2'}, {**row, 'user_id': 'dev', 'created_at': '2026-10-16T00:00:00'}]
        dates = ['2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09', '2026-10-14']
        logs = [{'workout_log_id': f'l{i}', 'user_id': 'u1', 'plan_id': None, 'workout_date': d,
                 'completion_status': 'completed'} for i, d in enumerate(dates)]
        client = FakeClient({'profiles': profiles, 'workout_logs': logs, 'exercises': []})
        original = seed.TEST_USER_COUNT
        seed.TEST_USER_COUNT = 2
        try:
            plan_rows, items, updates, new_exercises, summary = seed.seed(client, today=date(2026, 10, 23))
        finally:
            seed.TEST_USER_COUNT = original
        self.assertEqual([(p['user_id'], p['week_start']) for p in plan_rows],
                         [('u1', '2026-10-05'), ('u1', '2026-10-12'), ('u2', '2026-10-19')])
        self.assertEqual([(u['workout_log_id'], u['day_number']) for u in updates],
                         [('l0', 1), ('l1', 2), ('l2', 3), ('l3', None)])
        self.assertEqual({u['plan_id'] for u in updates}, {plan_rows[0]['plan_id']})
        self.assertEqual(summary['later logs left unlinked'], 1)
        self.assertEqual(summary['week 2: progress'], 1)
        self.assertEqual(len(new_exercises), 876)
        self.assertEqual({i['plan_id'] for i in items}, {p['plan_id'] for p in plan_rows})


if __name__ == '__main__':
    unittest.main()
