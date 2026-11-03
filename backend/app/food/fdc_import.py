"""Load USDA FoodData Central into Supabase so food search and lookups never call the FDC API.

    docker compose run --rm backend python -m app.food.fdc_import
    python -m app.food.fdc_import --files survey.zip sr_legacy.zip foundation.zip   # already downloaded

Imports FNDDS (survey foods), SR Legacy and Foundation from https://fdc.nal.usda.gov/download-datasets
(public domain): about 13,000 foods with kcal/protein/carbs/fat per 100 g and their portions. Needs
SUPABASE_URL / SUPABASE_KEY (the secret key) and backend/sql/007_food_search.sql. Safe to re-run;
re-run when USDA publishes a new FNDDS or Foundation release (update DATASETS below).
"""

import argparse
import io
import json
import os
import sys
import tempfile
import zipfile
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.food import lexicon
from app.food.fdc import Food, parse_food

DOWNLOAD_URL = "https://fdc.nal.usda.gov/fdc-datasets/"
DATASETS = [
    "FoodData_Central_survey_food_json_2024-10-31.zip",      # FNDDS 2021-2023
    "FoodData_Central_sr_legacy_food_json_2018-04.zip",      # final SR Legacy release
    "FoodData_Central_foundation_food_json_2026-04-30.zip",
]
BATCH = 500


# --- reading the downloads -------------------------------------------------------------

def read_foods(path: Path) -> Iterator[dict]:
    """Stream the foods out of a dataset zip ({"SurveyFoods": [{...}, ...]}) one at a time.
    SR Legacy is 200+ MB of JSON, so it isn't loaded in one go."""
    with zipfile.ZipFile(path) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".json"))
        with io.TextIOWrapper(zf.open(name), encoding="utf-8") as f:
            yield from (obj for obj in _stream_array(f) if isinstance(obj, dict))   # Foundation has a stray null


def _stream_array(f: io.TextIOBase, chunk_size: int = 1 << 20) -> Iterator[dict]:
    decoder = json.JSONDecoder()
    buf = ""
    while "[" not in buf:                 # skip '{"SurveyFoods": '
        more = f.read(chunk_size)
        if not more:
            return
        buf += more
    buf = buf[buf.index("[") + 1:]
    while True:
        buf = buf.lstrip(", \r\n\t")
        if buf.startswith("]"):
            return
        try:
            obj, end = decoder.raw_decode(buf)
        except json.JSONDecodeError:
            more = f.read(chunk_size)
            if not more:
                raise
            buf += more
            continue
        yield obj
        buf = buf[end:]


def usable(food: Food) -> bool:
    return food.per_100g.get("calories") is not None


# --- writing to Supabase ---------------------------------------------------------------

def food_row(food: Food, now: str) -> dict:
    return {
        "fdc_id": food.fdc_id, "description": food.description, "data_type": food.data_type,
        "calories_per_100g": food.per_100g.get("calories"), "protein_g_per_100g": food.per_100g.get("protein_g"),
        "carbs_g_per_100g": food.per_100g.get("carbs_g"), "fat_g_per_100g": food.per_100g.get("fat_g"),
        "other_nutrients": food.other_nutrients, "source": "import", "fetched_at": now,
    }


def portion_rows(food: Food) -> list[dict]:
    return [{"fdc_id": food.fdc_id, "fdc_portion_id": p.fdc_portion_id, "label": p.label[:200],
             "amount": p.amount, "gram_weight": round(p.gram_weight, 2)} for p in food.portions]


def write_batch(db, foods: list[Food]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db.table("fdc_foods").upsert([food_row(f, now) for f in foods], on_conflict="fdc_id").execute()
    ids = [f.fdc_id for f in foods]
    db.table("fdc_food_portions").delete().in_("fdc_id", ids).execute()
    portions = [row for f in foods for row in portion_rows(f)]
    for i in range(0, len(portions), BATCH * 4):
        db.table("fdc_food_portions").insert(portions[i:i + BATCH * 4]).execute()


def import_foods(db, raw_foods: Iterable[dict], log=print) -> int:
    count, batch = 0, []
    for raw in raw_foods:
        food = parse_food(raw)
        if not usable(food):
            continue
        batch.append(food)
        if len(batch) == BATCH:
            write_batch(db, batch)
            count += len(batch)
            batch = []
            log(f"  {count} foods")
    if batch:
        write_batch(db, batch)
        count += len(batch)
    return count


def missing_pinned(db) -> list[str]:
    """foods.json entries whose FDC id isn't in the local copy (they would need the API)."""
    pinned = {f.fdc_id: f.name for f in lexicon.foods().values()}
    present = set()
    ids = list(pinned)
    for i in range(0, len(ids), BATCH):
        rows = db.table("fdc_foods").select("fdc_id").in_("fdc_id", ids[i:i + BATCH]).execute().data
        present.update(r["fdc_id"] for r in rows)
    return sorted(f"{name} ({fid})" for fid, name in pinned.items() if fid not in present)


# --- command line ------------------------------------------------------------------------

def download(name: str, folder: Path) -> Path:
    path = folder / name
    if path.exists():
        return path
    print(f"downloading {name}")
    with httpx.stream("GET", DOWNLOAD_URL + name, timeout=120, follow_redirects=True) as res:
        res.raise_for_status()
        with open(path, "wb") as out:
            for chunk in res.iter_bytes():
                out.write(chunk)
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--files", nargs="+", type=Path, help="dataset zips you already downloaded")
    ap.add_argument("--dir", type=Path, help="where to download the zips (default: a temporary folder)")
    args = ap.parse_args(argv)

    from supabase import create_client
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
    if not url or not key:
        print("Set SUPABASE_URL and SUPABASE_KEY (the secret key), e.g. via docker compose / .env", file=sys.stderr)
        return 1
    db = create_client(url, key)

    with tempfile.TemporaryDirectory() as tmp:
        folder = args.dir or Path(tmp)
        folder.mkdir(parents=True, exist_ok=True)
        files = args.files or [download(name, folder) for name in DATASETS]
        total = 0
        for path in files:
            print(f"importing {path.name}")
            total += import_foods(db, read_foods(path))
    print(f"imported {total} foods")
    missing = missing_pinned(db)
    if missing:
        print(f"{len(missing)} foods.json entries aren't in the download (looked up via the API when used): "
              + ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
