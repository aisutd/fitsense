"""Evaluate the food recogniser on the hand-written test set (test_set.txt).

Compares three setups:
  model     - the trained spaCy NER alone
  lexicon   - only the food-list matcher (no machine learning), plus number/unit rules
  combined  - model + food-list matcher (what the app uses)
and reports precision / recall / F1 per label, with FOOD recall split into foods that are
in foods.json ("known") and foods the model has never seen ("unseen").

Usage (from backend/):
    python ml/food_ner/evaluate.py [--model app/food/model] [--show-errors]
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import spacy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from app.food import lexicon  # noqa: E402
from app.food.parser import MODEL_DIR, add_rules  # noqa: E402

LABELS = ("FOOD", "QTY", "UNIT")


def load_test_set() -> list[tuple[str, list[tuple[int, int, str]]]]:
    examples = []
    for line in (HERE / "test_set.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        text, spans, pos = "", [], 0
        for m in re.finditer(r"\[([^\]|]+)\|(FOOD|QTY|UNIT)\]", line):
            text += line[pos:m.start()]
            spans.append((len(text), len(text) + len(m.group(1)), m.group(2)))
            text += m.group(1)
            pos = m.end()
        text += line[pos:]
        examples.append((text, spans))
    return examples


def build(setup: str, model_dir: Path):
    if setup == "lexicon":
        nlp = spacy.blank("en")
        add_rules(nlp, with_numbers=True)
    else:
        nlp = spacy.load(model_dir)
        if setup == "combined":
            add_rules(nlp)
    return nlp


def score(nlp, examples, show_errors=False):
    tp, fp, fn = Counter(), Counter(), Counter()
    food_known, food_unseen = Counter(), Counter()
    errors = []
    for text, gold in examples:
        doc = nlp(text)
        pred = {(e.start_char, e.end_char, e.label_) for e in doc.ents}
        gold_set = set(gold)
        for s in pred & gold_set:
            tp[s[2]] += 1
        for s in pred - gold_set:
            fp[s[2]] += 1
        for s in gold_set - pred:
            fn[s[2]] += 1
        for s, e, label in gold:
            if label == "FOOD":
                bucket = food_known if lexicon.find_food(text[s:e]) else food_unseen
                bucket["total"] += 1
                bucket["hit"] += (s, e, label) in pred
        if pred != gold_set:
            errors.append((text, sorted(gold_set - pred), sorted(pred - gold_set)))

    rows = {}
    for label in LABELS + ("ALL",):
        t = sum(tp.values()) if label == "ALL" else tp[label]
        p_ = sum(fp.values()) if label == "ALL" else fp[label]
        n = sum(fn.values()) if label == "ALL" else fn[label]
        precision = t / (t + p_) if t + p_ else 0
        recall = t / (t + n) if t + n else 0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
        rows[label] = (precision, recall, f1)
    rows["known"] = food_known["hit"] / max(food_known["total"], 1)
    rows["unseen"] = food_unseen["hit"] / max(food_unseen["total"], 1)
    rows["counts"] = (food_known["total"], food_unseen["total"])
    if show_errors:
        for text, missed, extra in errors:
            print(f"  {text}")
            print(f"      missed: {[(text[s:e], l) for s, e, l in missed]}")
            print(f"      extra:  {[(text[s:e], l) for s, e, l in extra]}")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, default=MODEL_DIR)
    ap.add_argument("--show-errors", action="store_true")
    ap.add_argument("--only", choices=["model", "lexicon", "combined"])
    args = ap.parse_args()

    examples = load_test_set()
    print(f"{len(examples)} test sentences, exact-span matching\n")
    print(f"{'setup':10} {'label':5} {'precision':>9} {'recall':>7} {'F1':>6}")
    for setup in ([args.only] if args.only else ["lexicon", "model", "combined"]):
        rows = score(build(setup, args.model), examples, args.show_errors)
        for label in LABELS + ("ALL",):
            p, r, f = rows[label]
            print(f"{setup:10} {label:5} {p:9.1%} {r:7.1%} {f:6.1%}")
        known, unseen = rows["counts"]
        print(f"{setup:10} FOOD recall: known foods {rows['known']:.1%} (n={known}), unseen foods {rows['unseen']:.1%} (n={unseen})\n")


if __name__ == "__main__":
    main()
