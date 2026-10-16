"""Pin every food in app/food/data/foods.json to a FoodData Central id.

Runs each food's `query` through the same search + ranking the app uses and writes the
top match's fdc_id and description back into foods.json. Review the printed table (and
the diff) afterwards: fix a bad match by editing that food's `query` and re-running, or
set `fdc_id` by hand and add "pinned": true so it's never overwritten.

Usage (from backend/, with FDC_API_KEY set):
    python ml/food_ner/resolve_lexicon.py            # only foods without an fdc_id
    python ml/food_ner/resolve_lexicon.py --all      # re-resolve everything not pinned
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.food.fdc import FdcClient, match_confidence  # noqa: E402

FOODS_PATH = Path(__file__).resolve().parents[2] / "app" / "food" / "data" / "foods.json"


def main():
    redo_all = "--all" in sys.argv
    data = json.loads(FOODS_PATH.read_text(encoding="utf-8"))
    client = FdcClient()
    for food in data["foods"]:
        if food.get("pinned") or (food.get("fdc_id") and not redo_all):
            continue
        ranked = client.search_ranked(food["query"])
        if not ranked:
            print(f"!! {food['name']:28} no results for '{food['query']}'")
            continue
        top = ranked[0]
        food["fdc_id"], food["fdc_description"] = top.fdc_id, top.description
        conf = match_confidence(food["query"], ranked)
        flag = "  " if conf >= 0.7 else "??"
        print(f"{flag} {food['name']:28} -> {top.description[:60]:60} [{top.data_type[:6]}] {top.calories_per_100g:>5} kcal  conf {conf}")
    write_foods(data)


def write_foods(data: dict) -> None:
    """One food per line, so diffs stay readable."""
    lines = ",\n".join(f"    {json.dumps(f, ensure_ascii=False)}" for f in data["foods"])
    FOODS_PATH.write_text(
        f'{{\n  "_about": {json.dumps(data["_about"])},\n  "foods": [\n{lines}\n  ]\n}}\n', encoding="utf-8"
    )


if __name__ == "__main__":
    main()
