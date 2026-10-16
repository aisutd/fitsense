"""Record real FoodData Central responses for the offline tests.

Usage (from backend/, with FDC_API_KEY set):  python tests/fixtures/record_fdc.py
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from app.food import lexicon  # noqa: E402
from app.food.fdc import EXTRA_NUTRIENTS, FALLBACK_TYPES, NUTRIENTS, PREFERRED_TYPES, FdcClient  # noqa: E402

KEEP = set(NUTRIENTS) | set(EXTRA_NUTRIENTS)


def _number(n: dict) -> str | None:
    return n.get("nutrientNumber") or (n.get("nutrient") or {}).get("number")


def trim_food(d: dict) -> dict:
    """Only the fields the app reads, so fixtures stay small."""
    return {
        **{k: d.get(k) for k in ("fdcId", "description", "dataType", "publicationDate", "brandOwner", "gtinUpc") if k in d},
        "foodNutrients": [n for n in d.get("foodNutrients", []) if _number(n) in KEEP],
        "foodPortions": d.get("foodPortions", []),
    }


def trim_search(d: dict) -> dict:
    return {"foods": [{**{k: f.get(k) for k in ("fdcId", "description", "dataType", "score")},
                       "foodNutrients": [n for n in f.get("foodNutrients", []) if _number(n) == "208"]}
                      for f in d.get("foods", [])]}

FOODS = ["egg", "olive oil", "cheddar cheese", "banana", "white bread", "peanut butter", "pizza", "bacon",
         "protein powder", "coffee", "milk", "white rice", "chicken breast", "broccoli", "oatmeal", "cola",
         "tofu", "mixed vegetables", "vegetable oil", "soy sauce", "fried rice", "latte", "jam", "almonds", "apple"]
SEARCHES = ["kimchi fried rice", "pho", "shakshuka", "xyzzy", "banana"]


def main():
    c = FdcClient()
    out = HERE / "fdc"
    out.mkdir(exist_ok=True)
    for name in FOODS:
        fid = lexicon.foods()[name].fdc_id
        data = trim_food(c._request("GET", f"/food/{fid}"))
        (out / f"food_{fid}.json").write_text(json.dumps(data), encoding="utf-8")
    for q in SEARCHES:
        results = {}
        for label, types in (("preferred", PREFERRED_TYPES), ("fallback", FALLBACK_TYPES)):
            results[label] = trim_search(c._request("POST", "/foods/search", json={"query": q, "dataType": types, "pageSize": 25}))
        (out / f"search_{q.replace(' ', '_')}.json").write_text(json.dumps(results), encoding="utf-8")
        # the foods the app will fetch for the best-ranked hits
        from app.food.fdc import SearchHit, rank_hits
        hits = [SearchHit(f["fdcId"], f["description"], f["dataType"],
                          next((n.get("value") for n in f["foodNutrients"]), None), float(f.get("score") or 0))
                for group in results.values() for f in group["foods"]]
        for h in rank_hits(q, hits)[:5]:
            path = out / f"food_{h.fdc_id}.json"
            if not path.exists():
                path.write_text(json.dumps(trim_food(c._request("GET", f"/food/{h.fdc_id}"))), encoding="utf-8")
    print(f"recorded {len(FOODS)} foods and {len(SEARCHES)} searches in {out}")


if __name__ == "__main__":
    main()
