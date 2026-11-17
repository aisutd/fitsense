"""The System's achievements: out-of-the-ordinary things a player does, announced with some attitude.

Each achievement is awarded once. It has a title, a dry one-line description under it, a factual
`plain` line (for players who turn the attitude off), two or three lines of commentary from the System
(one is picked per player), and a reward from its rarity. Hidden ones show as "???" with a hint until
earned. Achievements for unhealthy extremes (very short sleep, skipped workouts, a terrible day) get a
line but no reward, and nothing here is about eating less or body weight.

A check takes the evaluation context (achievement_service.Context) and returns None when the
achievement isn't earned, or a dict of facts ({} if none) that fill the {placeholders} in its text.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

RARITIES = ["common", "uncommon", "rare", "epic", "legendary"]
# (XP, FitCoins) per rarity
REWARDS = {"common": (10, 5), "uncommon": (25, 15), "rare": (60, 40), "epic": (150, 100), "legendary": (300, 250)}

# What can trigger a check: one kind of log, any log, or something on the League tab.
LOG_TRIGGERS = {"workout", "sleep", "activity", "meal"}

BREAKFAST_WORDS = ("pancake", "waffle", "cereal", "omelet", "omelette", "french toast", "oatmeal", "bagel",
                   "scrambled egg", "breakfast", "granola", "porridge")
DESSERT_WORDS = ("cake", "ice cream", "cookie", "brownie", "donut", "doughnut", "cupcake", "pie", "cheesecake",
                 "pudding", "sundae")


@dataclass(frozen=True)
class Achievement:
    code: str
    name: str
    rarity: str
    category: str
    triggers: frozenset
    check: Callable
    description: str          # the dry one-liner under the title
    plain: str                # what it's for, without the attitude
    lines: tuple              # the System's commentary
    hidden: bool = True
    hint: str = ""            # shown as "???" until earned
    rewarded: bool = True

    @property
    def reward(self) -> tuple[int, int]:
        return REWARDS[self.rarity] if self.rewarded else (0, 0)


# --- helpers ---------------------------------------------------------------------------

def _days_back(day: date, n: int) -> list[date]:
    """day and the n-1 days before it, newest first."""
    return [day - timedelta(days=i) for i in range(n)]


def _contains(name: str | None, words) -> bool:
    text = (name or "").lower()
    return any(word in text for word in words)


def _streak(days: set, end: date) -> int:
    n = 0
    while end - timedelta(days=n) in days:
        n += 1
    return n


# --- activity ----------------------------------------------------------------------------

def _steps(c):
    return c.steps_on(c.day)


def couch_defense(c):
    s = _steps(c)
    return {} if s is not None and s < 1000 else None


def accidental_marathon(c):
    s = _steps(c)
    return {"steps": f"{s:,}"} if s is not None and s >= 30000 else None


def precisely_the_minimum(c):
    s, goal = _steps(c), c.goals["daily_steps"]
    return {"steps": f"{s:,}"} if s is not None and goal <= s <= goal + 50 else None


def palindrome_pedestrian(c):
    s = _steps(c)
    return {"steps": f"{s:,}"} if s is not None and s >= 1000 and str(s) == str(s)[::-1] else None


def suspiciously_round(c):
    s = _steps(c)
    return {"steps": f"{s:,}"} if s is not None and s >= 1000 and s % 1000 == 0 else None


# --- sleep (c.day is the night the sleep started) -----------------------------------------

def _hours(c, night=None):
    row = c.sleep_on(night or c.day)
    return float(row["hours_slept"]) if row and row.get("hours_slept") is not None else None


def _fmt_hours(h: float) -> str:
    return f"{h:g}"


def sleep_of_the_dead(c):
    h = _hours(c)
    return {"hours": _fmt_hours(h)} if h is not None and h >= 10 else None


def running_on_fumes(c):
    h = _hours(c)
    return {"hours": _fmt_hours(h)} if h is not None and 0 < h < 4 else None


def metronome(c):
    nights = [_hours(c, d) for d in _days_back(c.day, 5)]
    if None in nights or len(set(nights)) != 1:
        return None
    return {"hours": _fmt_hours(nights[0])}


def well_rested(c):
    target = float(c.goals["sleep_target_hours"])
    nights = [_hours(c, d) for d in _days_back(c.day, 7)]
    return {} if all(h is not None and h >= target for h in nights) else None


def haunted_mattress(c):
    row = c.sleep_on(c.day)
    return {} if row and row.get("sleep_quality") == 1 else None


# --- meals -------------------------------------------------------------------------------

def _dinners(c, day):
    return [m.get("display_name") or "" for m in c.meals_on(day) if m.get("meal_type") == "dinner"]


def creature_of_habit(c):
    days = [{n.strip().lower(): n for n in _dinners(c, d) if n.strip()} for d in _days_back(c.day, 5)]
    if not all(days):
        return None
    shared = set.intersection(*(set(d) for d in days))
    return {"meal": days[0][sorted(shared)[0]]} if shared else None


def snack_attack(c):
    count = sum(1 for m in c.meals_on(c.day) if m.get("meal_type") == "snack")
    return {"count": count} if count >= 5 else None


def protein_devotee(c):
    target = float(c.goals["nutrition"]["protein_g"] or 0)
    if target <= 0:
        return None
    for d in _days_back(c.day, 7):
        total = sum(float(m.get("protein_g") or 0) for m in c.meals_on(d))
        if total < target:
            return None
    return {}


def breakfast_for_dinner(c):
    meal = next((n for n in _dinners(c, c.day) if _contains(n, BREAKFAST_WORDS)), None)
    return {"meal": meal} if meal else None


def pizza_vegetable(c):
    for d in _days_back(c.day, 3):
        if not any(_contains(m.get("display_name"), ("pizza",)) for m in c.meals_on(d)):
            return None
    return {}


def full_menu(c):
    kinds = {m.get("meal_type") for m in c.meals_on(c.day)}
    return {} if {"breakfast", "lunch", "dinner", "snack"} <= kinds else None


def tasting_menu(c):
    week = []
    for d in _days_back(c.day, 7):
        names = {n.strip().lower() for n in _dinners(c, d) if n.strip()}
        if not names:
            return None
        week.append(names)
    every = [n for names in week for n in names]
    return {} if len(set(every)) == len(every) else None


def dessert_first(c):
    meal = next((m.get("display_name") for m in c.meals_on(c.day)
                 if m.get("meal_type") == "breakfast" and _contains(m.get("display_name"), DESSERT_WORDS)), None)
    return {"meal": meal} if meal else None


def food_critic(c):
    return {} if all(c.meals_on(d) for d in _days_back(c.day, 14)) else None


# --- workouts ----------------------------------------------------------------------------

def _week(day: date) -> list[date]:
    monday = day - timedelta(days=day.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def _completed_this_week(c):
    days = set(_week(c.day))
    return [w for w in c.workouts if c.date_of(w["workout_date"]) in days and w["completion_status"] == "completed"]


def plan_what_plan(c):
    planned = c.plan_days()
    return {} if planned and len(_completed_this_week(c)) == planned + 1 else None


def overachiever(c):
    planned = c.plan_days()
    return {} if planned and len(_completed_this_week(c)) >= planned + 2 else None


def speedrun(c):
    planned = c.plan_days()
    return {} if planned and planned >= 3 and c.day.weekday() <= 2 and len(_completed_this_week(c)) >= planned else None


def weekend_warrior(c):
    done = _completed_this_week(c)
    if c.day.weekday() < 5 or len(done) < 2:
        return None
    return {} if all(c.date_of(w["workout_date"]).weekday() >= 5 for w in done) else None


def ghosted_the_gym(c):
    recent = [w for w in c.workouts if c.date_of(w["workout_date"]) <= c.day][-3:]
    return {} if len(recent) == 3 and all(w["completion_status"] == "skipped" for w in recent) else None


def _today_completed(c):
    return [w for w in c.workouts if c.date_of(w["workout_date"]) == c.day and w["completion_status"] == "completed"]


def lost_track_of_time(c):
    longest = max((w.get("duration_minutes") or 0 for w in _today_completed(c)), default=0)
    return {"minutes": longest} if longest >= 150 else None


def blink_workout(c):
    short = [w["duration_minutes"] for w in _today_completed(c) if w.get("duration_minutes") and w["duration_minutes"] <= 10]
    return {"minutes": short[0]} if short else None


def double_feature(c):
    return {} if len(_today_completed(c)) >= 2 else None


# --- any log -----------------------------------------------------------------------------

def back_from_the_dead(c):
    last = c.last_log_before(c.log_day)
    gap = (c.log_day - last).days - 1 if last else 0
    return {"days": gap} if gap >= 7 else None


def _complete_day_score(c):
    result = c.day_score()
    if not result or result.get("overall_score") is None or result.get("provisional"):
        return None
    return result["overall_score"]


def perfect_day(c):
    return {} if _complete_day_score(c) == 100 else None


def rock_bottom(c):
    s = _complete_day_score(c)
    return {"score": s} if s is not None and s < 30 else None


def perfectly_balanced(c):
    return {} if _complete_day_score(c) == 50 else None


def unreasonably_consistent(c):
    return {} if (c.extra.get("checkin_streak") or 0) >= 30 else None


def system_is_impressed(c):
    return {} if (c.extra.get("checkin_streak") or 0) >= 100 else None


# --- league and shop (facts come from the endpoint in c.extra) -----------------------------

def promoted(c):
    before, now = c.extra.get("previous_tier"), c.extra.get("tier")
    return {"league": c.extra["league"]} if before is not None and now is not None and now > before else None


def relegated(c):
    before, now = c.extra.get("previous_tier"), c.extra.get("tier")
    return {"league": c.extra["league"]} if before is not None and now is not None and now < before else None


def king_of_the_hill(c):
    return {} if c.extra.get("position") == 1 and (c.extra.get("members") or 0) >= 5 else None


def final_boss(c):
    return {} if c.extra.get("tier") == 8 else None


def big_spender(c):
    return {} if c.extra.get("purchased") else None


def identity_crisis(c):
    return {"count": c.extra["changes_today"]} if (c.extra.get("changes_today") or 0) >= 3 else None


def completionist_wardrobe(c):
    return {} if c.extra.get("owns_every_avatar") else None


def _a(code, name, rarity, category, triggers, check, description, plain, lines, **kw):
    return Achievement(code, name, rarity, category, frozenset(triggers), check, description, plain, tuple(lines), **kw)


ANY_LOG = LOG_TRIGGERS

ACHIEVEMENTS: list[Achievement] = [
    # activity
    _a("couch_defense", "Couch Defense Champion", "common", "activity", {"activity"}, couch_defense,
       "Took fewer than 1,000 steps in a day. The couch held its ground.",
       "Fewer than 1,000 steps in a day.",
       ["The System has reviewed today's footage. It is mostly ceiling. No reward. The System does not negotiate with sofas.",
        "Fewer than a thousand steps. Somewhere, a pedometer is filing for unemployment. No reward, but tomorrow is a fresh floor."],
       hint="The couch remembers.", rewarded=False),
    _a("accidental_marathon", "Accidental Marathon", "rare", "activity", {"activity"}, accidental_marathon,
       "{steps} steps in one day. Nobody does that on purpose.",
       "30,000+ steps in one day.",
       ["{steps} steps. The System assumes you were being chased and would like to know by what.",
        "Your shoes have requested hazard pay. The System said no, and gave the money to you instead."],
       hidden=False),
    _a("precisely_the_minimum", "Precisely the Minimum", "rare", "activity", {"activity"}, precisely_the_minimum,
       "Beat your step goal by fewer than 50 steps. Surgical.",
       "Hit your step goal with under 50 steps to spare.",
       ["You cleared your goal by a margin the System needed a microscope to see. Efficiency is a virtue. Technically.",
        "Not one step more than necessary. The System suspects you paced the hallway watching the counter. The System would have done the same."],
       hint="Just enough is still enough."),
    _a("palindrome_pedestrian", "Palindrome Pedestrian", "rare", "activity", {"activity"}, palindrome_pedestrian,
       "{steps} steps. Reads the same backwards. You absolutely did not plan this.",
       "A step count that reads the same backwards (like 12,321).",
       ["{steps}. Forwards, backwards, the System checked both. Statistically unremarkable. Aesthetically perfect.",
        "A palindromic step count. The System has no idea how you did this and refuses to believe it was luck."],
       hint="Some numbers walk both ways."),
    _a("suspiciously_round", "Suspiciously Round", "uncommon", "activity", {"activity"}, suspiciously_round,
       "Exactly {steps} steps. Nature does not produce round numbers.",
       "A step count that's an exact multiple of 1,000.",
       ["Exactly {steps}. Not one more, not one less. The System knows a preset button when it sees one. Rewarded anyway, for confidence.",
        "The System has walked many imaginary miles and never once landed on a round number. Congratulations on your very precise, totally real day."],
       hint="Nature hates a round number."),
    # sleep
    _a("sleep_of_the_dead", "The Sleep of the Dead", "common", "sleep", {"sleep"}, sleep_of_the_dead,
       "Slept {hours} hours. Pulse confirmed. Barely.",
       "Slept 10 or more hours in one night.",
       ["{hours} hours. The System checked on you twice. You were fine. You were also snoring.",
        "You slept long enough to dream a sequel. Rested is rested."],
       hint="Some nights are longer than others."),
    _a("running_on_fumes", "Running on Fumes", "common", "sleep", {"sleep"}, running_on_fumes,
       "Under four hours of sleep. The System isn't impressed. It's concerned.",
       "Slept under 4 hours in one night.",
       ["{hours} hours. No reward for this one. The System would rather you went to bed. Tonight, perhaps?",
        "The System has filed this short night under 'please don't'. Sleep is not a side quest. No reward."],
       hint="The night was short. Too short.", rewarded=False),
    _a("metronome", "The Metronome", "rare", "sleep", {"sleep"}, metronome,
       "Slept exactly {hours} hours five nights in a row. Are you a clock?",
       "The exact same hours of sleep five nights running.",
       ["Five nights at precisely {hours} hours. The System has begun to suspect you are a very committed appliance.",
        "Same hours, five nights straight. Your body clock has a metronome and the System is mildly jealous."],
       hint="Tick. Tock. Tick. Tock."),
    _a("well_rested", "Suspiciously Well Rested", "uncommon", "sleep", {"sleep"}, well_rested,
       "Hit your sleep target seven nights in a row. Who are you?",
       "Hit your sleep target 7 nights in a row.",
       ["A full week of proper sleep. The System ran a diagnostic on itself to make sure it wasn't seeing things.",
        "Seven nights on target. Your future self says thanks. Your past self is confused."],
       hint="Seven nights of doing it right."),
    _a("haunted_mattress", "Haunted Mattress", "common", "sleep", {"sleep"}, haunted_mattress,
       "Rated your sleep 1 out of 5. Something under the bed is winning.",
       "Rated a night's sleep 1 out of 5.",
       ["One star. The System has filed a formal complaint against your mattress. Here's a consolation prize.",
        "Rough night. The System can't fix your pillow, but it can give you coins, and coins are almost a pillow."],
       hint="Rate the night honestly."),
    # meals
    _a("creature_of_habit", "Creature of Habit", "common", "nutrition", {"meal"}, creature_of_habit,
       "Had {meal} for dinner five nights running.",
       "The same dinner five days in a row.",
       ["Five nights of {meal}. The System admires the commitment and has quietly informed your taste buds.",
        "{meal}, again. The System isn't judging. The System is simply counting. It's at five."],
       hint="Same time, same place, same plate."),
    _a("snack_attack", "Snack Attack", "common", "nutrition", {"meal"}, snack_attack,
       "Logged {count} snacks in a single day. Strategic grazing.",
       "Logged 5 or more snacks in one day.",
       ["{count} snacks. The System respects anyone who refuses to be ruled by the tyranny of mealtimes.",
        "Breakfast, lunch and dinner are suggestions, as far as you're concerned. Snack count: {count}."],
       hint="A little something. Several times."),
    _a("protein_devotee", "Protein Devotee", "uncommon", "nutrition", {"meal"}, protein_devotee,
       "Hit your protein target seven days straight. Your muscles sent a thank-you card.",
       "Hit your protein target 7 days in a row.",
       ["Seven days on your protein target. The System has no muscles and still felt a twinge of pride.",
        "A full week of protein. The System has informed the nation's chickens, who are not thrilled."],
       hint="A week of building blocks."),
    _a("breakfast_for_dinner", "Breakfast for Dinner", "uncommon", "nutrition", {"meal"}, breakfast_for_dinner,
       "Logged {meal} as dinner. Time is a construct.",
       "Logged a breakfast food as dinner.",
       ["{meal} for dinner. The System has updated its definition of 'evening' to accommodate you.",
        "Dinner was {meal}. Bold. Unbothered. The System approves of anyone who won't let a clock pick their food."],
       hint="Who says when breakfast ends?"),
    _a("pizza_vegetable", "Pizza Is a Vegetable", "common", "nutrition", {"meal"}, pizza_vegetable,
       "Pizza three days in a row. There's tomato in it. That counts.",
       "Logged pizza three days running.",
       ["Three straight days of pizza. The System ran the numbers and the numbers came back pepperoni.",
        "Pizza, pizza, pizza. The System notes that sauce is technically a vegetable and will allow it. This time."],
       hint="Three slices of a pattern."),
    _a("full_menu", "Full Menu", "common", "nutrition", {"meal"}, full_menu,
       "Breakfast, lunch, dinner and a snack in one day. The complete set.",
       "Logged breakfast, lunch, dinner and a snack in one day.",
       ["All four meal slots filled. The System loves a complete collection almost as much as you love lunch.",
        "Breakfast, lunch, dinner, snack. Every box ticked. The System's spreadsheet is delighted."],
       hint="Collect all four."),
    _a("tasting_menu", "Tasting Menu", "uncommon", "nutrition", {"meal"}, tasting_menu,
       "Seven different dinners in seven days. A food tour without the plane ticket.",
       "Seven different dinners in seven days.",
       ["Seven nights, seven dinners. The System had a bet going that you'd repeat. The System lost.",
        "A different dinner every night this week. Somewhere, a food critic is nervously updating their résumé."],
       hint="Never the same plate twice."),
    _a("dessert_first", "Dessert Course First", "common", "nutrition", {"meal"}, dessert_first,
       "Logged {meal} for breakfast. Living the dream.",
       "Logged a dessert as breakfast.",
       ["{meal} for breakfast. The System can't recommend it and can't stop you. A small reward, for honesty.",
        "Breakfast: {meal}. The System has seen bolder moves, but never before 9 a.m."],
       hint="The most important meal of the day, reimagined."),
    _a("food_critic", "Food Critic", "rare", "nutrition", {"meal"}, food_critic,
       "Logged meals fourteen days in a row. Every bite on the record.",
       "Logged meals 14 days in a row.",
       ["Two weeks of logged meals. The System now knows more about your lunches than your closest friends do.",
        "Fourteen days of food logs. The System would like to thank the snacks, who made this possible."],
       hidden=False),
    # workouts
    _a("plan_what_plan", "Plan? What Plan?", "uncommon", "workout", {"workout"}, plan_what_plan,
       "Trained after the week's plan was already done. The plan was very clear.",
       "Completed a workout after finishing the week's plan.",
       ["The plan was finished. The plan said rest. You read the plan, and chose violence anyway.",
        "An extra workout, entirely unscheduled. The System's carefully built plan is now officially 'advisory'."],
       hint="The plan said rest. You said no."),
    _a("overachiever", "Overachiever, Apparently", "rare", "workout", {"workout"}, overachiever,
       "Two workouts over plan in one week. The plan is nervous now.",
       "Two or more workouts beyond the week's plan.",
       ["Two workouts beyond the plan. The System will be making next week harder. You did this to yourself.",
        "You've lapped your own plan. The System is equal parts proud and concerned. Mostly proud."],
       hint="The plan is a floor, not a ceiling."),
    _a("speedrun", "Speedrun", "rare", "workout", {"workout"}, speedrun,
       "Finished the whole week's plan by Wednesday. Any% completion.",
       "Finished the week's plan by Wednesday.",
       ["Whole week's plan, done by Wednesday. The rest of the week is a victory lap, or a nap. The System supports both.",
        "Plan cleared by midweek. Speedrunners everywhere are studying your splits."],
       hint="Why wait for the weekend?"),
    _a("weekend_warrior", "Weekend Warrior", "uncommon", "workout", {"workout"}, weekend_warrior,
       "Every workout this week happened on Saturday or Sunday.",
       "All of a week's workouts were on the weekend.",
       ["Five days of rest, two days of fury. The System calls this a strategy. Your knees call it an ambush.",
        "All workouts, all weekend. The weekdays have filed a formal complaint about being ignored."],
       hint="Monday to Friday is someone else's problem."),
    _a("ghosted_the_gym", "Ghosted the Gym", "common", "workout", {"workout"}, ghosted_the_gym,
       "Skipped three workouts in a row. The gym stopped texting back.",
       "Skipped three workouts in a row.",
       ["Three skips in a row. The dumbbells have started a support group. No reward. The next workout breaks the spell.",
        "The gym hasn't heard from you in a while. It's fine. It's not crying. No reward this time."],
       hint="Three no-shows.", rewarded=False),
    _a("lost_track_of_time", "Lost Track of Time", "rare", "workout", {"workout"}, lost_track_of_time,
       "A {minutes}-minute workout. Did you move in?",
       "A workout of 150 minutes or more.",
       ["{minutes} minutes. The System assumed you were trapped under a barbell and was preparing a rescue.",
        "A {minutes}-minute session. The System is impressed and would like you to drink some water."],
       hint="Some sessions just keep going."),
    _a("blink_workout", "Blink and You Missed It", "common", "workout", {"workout"}, blink_workout,
       "A {minutes}-minute workout, completed. It counts. Technically.",
       "Completed a workout of 10 minutes or less.",
       ["{minutes} minutes. The System blinked and nearly missed it. It still counts, and the System is a stickler for counting.",
        "A workout so brief the System had to replay it in slow motion. Logged. Rewarded. Barely."],
       hint="Short and sweet."),
    _a("double_feature", "Double Feature", "uncommon", "workout", {"workout"}, double_feature,
       "Two completed workouts in one day. Matinee and evening show.",
       "Two completed workouts on the same day.",
       ["Two workouts in one day. The System has upgraded you from 'person who exercises' to 'person who should eat something'.",
        "Morning show, evening show. The System is selling tickets now."],
       hint="Once wasn't enough."),
    # any log
    _a("back_from_the_dead", "Back From the Dead", "uncommon", "consistency", ANY_LOG, back_from_the_dead,
       "Logged something after {days} days of radio silence.",
       "Logged something after 7 or more days with nothing.",
       ["Oh. You're back. The System had already started renting out your locker. Welcome home.",
        "{days} days of silence, and then this. The System never doubted you. The System doubted you a little."],
       hint="Gone, but not forgotten."),
    _a("perfect_day", "Perfect Day", "epic", "consistency", ANY_LOG, perfect_day,
       "A HealthScore of 100. Flawless. Suspiciously flawless.",
       "A daily HealthScore of 100.",
       ["One hundred out of one hundred. The System will spend the rest of the day looking for the catch.",
        "A perfect day. The System has framed it. Metaphorically. The System does not have walls."],
       hidden=False),
    _a("rock_bottom", "Rock Bottom, Respectfully", "common", "consistency", ANY_LOG, rock_bottom,
       "A full day's HealthScore of {score}. The only way is up. Literally.",
       "A complete day with a HealthScore under 30.",
       ["A rough one. The System is literally keeping score, but it's rooting for tomorrow. No reward.",
        "Today was a day. Tomorrow is another one. The System has saved you a seat at the comeback. No reward, yet."],
       hint="Everyone has one of these days.", rewarded=False),
    _a("perfectly_balanced", "Perfectly Balanced", "rare", "consistency", ANY_LOG, perfectly_balanced,
       "A HealthScore of exactly 50. Not a point more, not a point less.",
       "A complete day with a HealthScore of exactly 50.",
       ["Exactly fifty. Half great, half not. The System finds this deeply satisfying in a way it can't explain.",
        "Fifty out of a hundred, right down the middle. The System offers exactly half a compliment. And a reward."],
       hint="Right down the middle."),
    _a("unreasonably_consistent", "Unreasonably Consistent", "epic", "consistency", ANY_LOG, unreasonably_consistent,
       "Checked in 30 days in a row. The System is starting to rely on you.",
       "Logged something 30 days in a row.",
       ["Thirty days straight. The System has stopped checking whether you'll show up. You always do. It's a little unsettling.",
        "A month without missing a day. The System would give you a medal, but coins are better."],
       hidden=False),
    _a("system_is_impressed", "The System Is Impressed", "legendary", "consistency", ANY_LOG, system_is_impressed,
       "One hundred days in a row. This almost never happens.",
       "Logged something 100 days in a row.",
       ["One hundred consecutive days. The System does not say this lightly, or often, or ever: well done.",
        "A hundred days. The System has revised its expectations of humanity. Slightly upward."],
       hidden=False),
    # league
    _a("promoted", "Moving On Up", "rare", "league", {"league"}, promoted,
       "Promoted to {league}. The air is thinner up here.",
       "Moved up a league.",
       ["Welcome to {league}. The System has rolled out a small carpet. It is red. It is pixelated. Enjoy.",
        "Promoted to {league}. Your old league misses you. Your new one has no idea what's coming."],
       hidden=False),
    _a("relegated", "Strategic Retreat", "common", "league", {"league"}, relegated,
       "Dropped to {league}. Totally on purpose. Obviously.",
       "Moved down a league.",
       ["Relegated to {league}. The System calls it 'strategic regrouping'. Here's a little something for the trip.",
        "Down to {league}. The System has watched many comebacks start exactly here. Consolation coins enclosed."],
       hint="The ladder goes both ways."),
    _a("king_of_the_hill", "King of the Hill", "epic", "league", {"league"}, king_of_the_hill,
       "First place in your league. Everyone else is looking up.",
       "First place in your league's standings.",
       ["Number one. The System has enlarged the leaderboard font to fit your ego.",
        "Top of the league. The view is excellent. Please don't let it go to your head. Too late."],
       hidden=False),
    _a("final_boss", "Final Boss", "legendary", "league", {"league"}, final_boss,
       "Reached Sapphire, the top league. There's nowhere left to climb.",
       "Reached the Sapphire league.",
       ["Sapphire. The top. The System has nothing left to promote you to and is frankly worried about that.",
        "You made the final league. Somewhere in Bronze, they tell stories about you."],
       hidden=False),
    # shop
    _a("big_spender", "Big Spender", "uncommon", "shop", {"shop"}, big_spender,
       "Bought your first avatar. Retail therapy, but for your face.",
       "Bought your first avatar.",
       ["First purchase complete. The System's economy thanks you for your participation.",
        "Coins, spent on a new look. The System approves. Vanity is a valid stat."],
       hint="Coins are for spending."),
    _a("identity_crisis", "Identity Crisis", "common", "shop", {"avatar"}, identity_crisis,
       "Changed your avatar {count} times in one day. Who are you, really?",
       "Changed your avatar 3 times in one day.",
       ["Three different looks in one day. The System has opened a file titled 'Who is this person' and it's getting thick.",
        "New face, new face, new face. The System respects the journey of self-discovery. Please pick one."],
       hint="Mirror, mirror."),
    _a("completionist_wardrobe", "Completionist Wardrobe", "epic", "shop", {"shop"}, completionist_wardrobe,
       "Own every avatar in the shop. The shop is empty and slightly afraid of you.",
       "Own every avatar in the shop.",
       ["Every avatar, owned. The shopkeeper closed early and went home to think about things.",
        "You've bought out the whole wardrobe. The System will have to commission new outfits. Thanks a lot."],
       hint="Leave nothing on the shelf."),
]

BY_CODE = {a.code: a for a in ACHIEVEMENTS}
assert len(BY_CODE) == len(ACHIEVEMENTS), "achievement codes must be unique"
