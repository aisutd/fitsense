"""Generate labelled training data for the food recogniser (FOOD / QTY / UNIT).

Sentences are built from templates filled with foods from app/food/data/foods.json plus
extra training-only food names (for variety). 15% of foods are held out of the training
set and appear only in the dev set, so the dev score measures foods the model hasn't seen.
Nothing from test_set.txt is used: any food in the test set is removed from the training
vocabulary, and the script fails if one slips through.

Usage (from backend/):
    python ml/food_ner/generate_data.py            # writes ml/food_ner/corpus/{train,dev}.spacy
"""

import random
import re
import sys
from pathlib import Path

import spacy
from spacy.tokens import DocBin

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from app.food import lexicon  # noqa: E402
from app.food.text import prepare_text  # noqa: E402

SEED = 13
N_TRAIN, N_DEV = 9000, 1500

# Extra food names used only to teach the model what food looks like in context.
EXTRA_FOODS = {
    "dish": ["lo mein", "chow mein", "orange chicken", "general tso chicken", "beef stew", "pot roast", "meatloaf",
             "shepherds pie", "chicken alfredo", "fettuccine alfredo", "risotto", "paella", "gnocchi", "ravioli",
             "tortellini", "enchiladas", "fajitas", "tamales", "carnitas", "pozole", "gumbo", "jambalaya",
             "teriyaki chicken", "katsu curry", "udon", "soba noodles", "dal", "chana masala", "butter chicken",
             "palak paneer", "fish tacos", "lobster roll", "crab cakes", "meatballs", "chicken parm", "stuffed peppers",
             "pierogi", "goulash", "moussaka", "kebab", "souvlaki", "chicken shawarma", "banh mi", "cuban sandwich",
             "philly cheesesteak", "sloppy joe", "corn dog", "chicken pot pie", "quiche", "frittata", "crepes",
             "huevos rancheros", "breakfast sandwich", "egg mcmuffin", "chicken teriyaki bowl", "burrito bowl",
             "grain bowl", "buddha bowl", "veggie burger", "turkey burger", "chicken tenders", "fish sticks",
             "tuna casserole", "baked ziti", "minestrone", "tomato soup", "french onion soup", "vegetable soup",
             "mapo tofu", "kung pao chicken", "sweet and sour pork", "egg fried rice", "dan dan noodles",
             "massaman curry", "green curry", "laksa", "nasi goreng", "adobo", "lumpia", "pancit"],
    "fruit": ["nectarine", "plum", "apricot", "fig", "guava", "lychee", "passion fruit", "dragon fruit",
              "honeydew", "grapefruit", "tangerine", "persimmon", "starfruit", "cranberries", "goji berries"],
    "vegetable": ["cabbage", "beets", "radishes", "artichoke", "leeks", "arugula", "collard greens", "okra",
                  "snap peas", "butternut squash", "pumpkin", "parsnips", "turnips", "jalapenos", "scallions"],
    "protein": ["lamb chops", "duck breast", "venison", "bison burger", "sardines", "mackerel", "trout",
                "scallops", "mussels", "calamari", "turkey bacon", "chorizo", "salami", "prosciutto", "pepperoni",
                "pulled pork", "brisket", "ribs", "pork belly", "seitan", "veggie sausage", "egg salad"],
    "grain": ["barley", "bulgur", "farro", "millet", "polenta", "wild rice", "rice noodles", "egg noodles",
              "muesli", "bran flakes", "frosted flakes", "rice krispies", "special k"],
    "bread": ["brioche", "ciabatta", "focaccia", "rye bread", "pumpernickel", "dinner roll", "hamburger bun",
              "hot dog bun", "flatbread", "lavash", "biscuit", "scone"],
    "snack": ["trail mix bar", "pita chips", "veggie straws", "cheese crackers", "goldfish crackers",
              "fruit snacks", "fruit leather", "seaweed snacks", "dried mango", "banana chips", "graham crackers"],
    "sweet": ["cupcake", "pie", "apple pie", "pumpkin pie", "macarons", "eclair", "cinnamon roll", "churros",
              "gelato", "frozen yogurt", "pudding", "jello", "fudge", "gummy bears", "candy bar", "snickers",
              "oreos", "pop tart", "cannoli"],
    "drink": ["lemonade", "iced tea", "sweet tea", "chocolate milk", "coconut water", "sparkling water",
              "ginger ale", "root beer", "cold brew", "espresso", "mocha", "frappuccino", "horchata",
              "hot cider", "cranberry juice", "grape juice", "vegetable juice", "kefir", "lassi"],
    "dairy": ["goat cheese", "brie", "gouda", "provolone", "pepper jack", "cheese curds", "skyr", "creme fraiche"],
    "spread": ["tahini", "pesto", "apple butter", "marmalade", "agave", "sunflower butter"],
    "condiment": ["sriracha mayo", "tzatziki", "teriyaki sauce", "hoisin sauce", "gravy", "alfredo sauce",
                  "blue cheese dressing", "honey mustard", "relish"],
    "nut": ["pecans", "pistachios", "macadamia nuts", "hazelnuts", "brazil nuts", "pumpkin seeds", "flax seeds"],
}

# Units that make sense per food category: (canonical unit, typical quantities)
CATEGORY_UNITS = {
    "protein": [("g", [85, 100, 120, 150, 170, 200, 250]), ("oz", [3, 4, 5, 6, 8]), ("piece", [1, 2, 3]), ("slice", [2, 3, 4]), ("serving", [1, 2])],
    "dairy": [("cup", [0.5, 1]), ("g", [30, 50, 100, 150, 170, 200]), ("slice", [1, 2]), ("oz", [1, 2]), ("tbsp", [1, 2])],
    "drink": [("cup", [1, 2]), ("glass", [1, 2]), ("can", [1, 2]), ("bottle", [1]), ("ml", [250, 330, 500]), ("oz", [8, 12, 16]), ("large", [1]), ("small", [1]), ("medium", [1])],
    "fat": [("tsp", [1, 2]), ("tbsp", [1, 2])],
    "grain": [("cup", [0.5, 1, 1.5, 2]), ("bowl", [1, 2]), ("g", [50, 100, 150, 200]), ("serving", [1])],
    "bread": [("slice", [1, 2, 3]), ("piece", [1, 2])],
    "vegetable": [("cup", [0.5, 1, 2]), ("g", [50, 80, 100, 150]), ("handful", [1, 2]), ("serving", [1])],
    "fruit": [("cup", [0.5, 1, 2]), ("medium", [1, 2]), ("large", [1]), ("small", [1, 2]), ("slice", [2, 3]), ("handful", [1])],
    "nut": [("handful", [1, 2]), ("oz", [1, 2]), ("g", [20, 30, 50]), ("tbsp", [1, 2]), ("cup", [0.25])],
    "snack": [("handful", [1, 2]), ("bag", [1]), ("oz", [1, 2]), ("g", [30, 50]), ("piece", [1, 2]), ("cup", [1, 2])],
    "sweet": [("piece", [1, 2]), ("slice", [1, 2]), ("scoop", [1, 2, 3]), ("bar", [1])],
    "spread": [("tbsp", [1, 2]), ("tsp", [1, 2])],
    "condiment": [("tbsp", [1, 2]), ("tsp", [1, 2]), ("cup", [0.25])],
    "dish": [("plate", [1]), ("bowl", [1, 2]), ("serving", [1, 2]), ("slice", [1, 2, 3]), ("piece", [1, 2]), ("cup", [1, 2])],
    "supplement": [("scoop", [1, 2]), ("g", [30])],
}
COUNTABLE = {"fruit", "protein", "bread", "sweet", "dish", "snack"}

# canonical unit -> (forms used for one, forms used for more than one); "X of" also adds "of"
UNIT_FORMS = {
    "g": (["g", "grams", "g of", "grams of"],) * 2, "oz": (["oz", "ounces", "oz of"],) * 2, "ml": (["ml", "ml of"],) * 2,
    "cup": (["cup", "cup of"], ["cups", "cups of"]), "tbsp": (["tbsp", "tablespoon", "tbsp of", "tablespoon of"], ["tbsp", "tablespoons", "tbsp of", "tablespoons of"]),
    "tsp": (["tsp", "teaspoon", "tsp of"], ["tsp", "teaspoons", "tsp of"]), "slice": (["slice", "slice of"], ["slices", "slices of"]),
    "piece": (["piece", "piece of"], ["pieces", "pieces of"]), "serving": (["serving of", "portion of"], ["servings of", "servings"]),
    "bowl": (["bowl of", "bowl"], ["bowls of"]), "plate": (["plate of", "plateful of"], ["plates of"]),
    "glass": (["glass of"], ["glasses of"]), "can": (["can of"], ["cans of"]), "bottle": (["bottle of"], ["bottles of"]),
    "handful": (["handful of"], ["handfuls of"]), "scoop": (["scoop of", "scoop"], ["scoops of", "scoops"]),
    "bag": (["bag of", "small bag of"], ["bags of"]), "bar": (["bar of"], ["bars of"]),
    "large": (["large", "big"],) * 2, "medium": (["medium"],) * 2, "small": (["small"],) * 2,
}
SIZE = {"large", "medium", "small"}

NUM_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 8: "eight", 10: "ten", 12: "twelve"}

FRAMES = [
    "{items}", "{items}", "{items}", "I had {items}", "i had {items} for {meal}", "had {items}", "ate {items}",
    "just ate {items}", "{meal}: {items}", "{meal} - {items}", "{meal} was {items}", "For {meal} I had {items}",
    "for {meal} {items}", "I'm eating {items}", "eating {items} rn", "made {items} for {meal}", "grabbed {items}",
    "snacked on {items}", "I drank {items}", "{items} for {meal}", "{items} after the gym", "{items} before practice",
    "Today's {meal}: {items}", "my {meal} was {items}", "I ate {items} at the dining hall", "Ordered {items}",
    "had {items} again", "{items} lol", "Post workout: {items}", "cooked {items}", "{items} for dessert",
    "late night {items}", "had some {items}", "I just had {items}.", "{meal} today was {items}",
    "Ate {items} with friends", "we got {items}", "{items}, that's it", "quick {meal}: {items}",
    "grabbed {items} on the way to class", "{items} on top", "had {items} at home", "{items} with my roommate",
    "{items} after work", "{items} between classes", "had {items} at the cafe", "{items} on the go",
    "{items} in the car", "{items} at my desk", "{items} before bed", "{items} at the game",
]
# Sentences with no food at all, so the model learns not to tag everything as FOOD.
NEG_SUBJECTS = ["", "I ", "i ", "just ", "we ", "Today I ", "this morning I ", "yesterday I "]
NEG_ACTIONS = ["went to the gym", "went for a walk", "ran 3 miles", "did a 5k", "played soccer", "studied all day",
               "skipped lunch", "skipped dinner", "didn't eat yet", "haven't eaten", "was too busy to eat", "slept in",
               "walked the dog", "lifted weights", "did yoga", "went swimming", "worked late", "had a meeting",
               "forgot to eat", "fasted until noon", "went to class", "took a nap", "biked to campus", "cleaned my room",
               "watched a movie", "stretched for 20 minutes", "hit the gym after class", "played basketball for an hour"]
NEG_TAILS = ["", "", " today", " this morning", " again", " lol", " with friends", " after work", " before class", "."]
EXCLUDE_NEGATIVES = {"went for a run today"}   # used verbatim by tests/test_food_parser.py

# Activity context around a real meal ("ran 3 miles then had ...")
CONTEXT_FRAMES = ["{neg} then had {items}", "after I {neg_bare} I ate {items}", "{items} after I {neg_bare}",
                  "{neg} and grabbed {items}", "{neg}, then {items} for {meal}"]
# Words in front of a food that are not part of its name (left unlabelled)
LEADING = ["another", "my", "the", "more", "extra", "leftover", "homemade", "one more", "a second"]

MEALS = ["breakfast", "lunch", "dinner", "brunch", "a snack", "dessert", "supper", "pre workout"]
JOINERS = [(", ", 4), (" and ", 5), (", and ", 2), (" with ", 3), (" & ", 1), (" plus ", 1), (" + ", 1), ("; ", 1)]


class Builder:
    """Accumulates text and (start, end, label) spans."""

    def __init__(self):
        self.text, self.spans = "", []

    def add(self, s: str, label: str | None = None):
        if label:
            self.spans.append((len(self.text), len(self.text) + len(s), label))
        self.text += s


def pluralize(name: str) -> str:
    words = name.split()
    last = words[-1]
    if last.endswith(("s", "sh", "ch")) or last in ("rice", "milk", "bread", "cheese", "pasta", "tofu", "oatmeal"):
        return name
    last = last[:-1] + "ies" if re.search(r"[^aeiou]y$", last) else last + "s"
    return " ".join(words[:-1] + [last])


def qty_text(rng: random.Random, q: float) -> str:
    r = rng.random()
    if q == 0.5:
        return rng.choice(["1/2", "half a", "½", "0.5", "a half"]) if r < 0.9 else "half"
    if q == 0.25:
        return rng.choice(["1/4", "a quarter"])
    if q == 1.5:
        return rng.choice(["1.5", "1 1/2", "one and a half"])
    if q == int(q):
        q = int(q)
        if q in NUM_WORDS and r < 0.3:
            return NUM_WORDS[q]
        if q == 2 and r < 0.4:
            return "a couple"
        if q == 3 and r < 0.45:
            return rng.choice(["a few", "a few", "several"])
        if q in (2, 3) and r < 0.6:
            return rng.choice(["2-3", "3-4", "2 or 3", "1-2"])
        if q == 12 and r < 0.5:
            return "a dozen"
        return str(q)
    return f"{q:g}"


def add_qty(b: Builder, rng: random.Random, q: float):
    """QTY span; 'half a' style phrases label only the number word."""
    t = qty_text(rng, q)
    if t.endswith(" a"):                       # "half a" -> [half] a
        b.add(t[:-2], "QTY")
        b.add(" a")
    else:
        b.add(t, "QTY")


def add_unit(b: Builder, rng: random.Random, unit: str, plural: bool = False):
    form = rng.choice(UNIT_FORMS[unit][1 if plural else 0])
    word, _, rest = form.partition(" of")
    word = word.strip()
    if unit == "bag" and word.startswith("small "):
        b.add("small ")
        word = "bag"
    b.add(word, "UNIT")
    if _:
        b.add(" of")


def add_item(b: Builder, rng: random.Random, food: str, category: str, dishes: list[str]):
    units = CATEGORY_UNITS.get(category, CATEGORY_UNITS["dish"])
    r = rng.random()
    if r < 0.24:                                             # bare, sometimes "another banana"
        if rng.random() < 0.2:
            b.add(rng.choice(LEADING) + " ")
        b.add(food, "FOOD")
    elif r < 0.36:                                           # a/an/some food
        art = rng.choice(["some", "an" if food[0] in "aeiou" else "a"])
        b.add(art + " ")
        b.add(food, "FOOD")
    elif r < 0.52 and category in COUNTABLE:                 # 3 eggs
        q = rng.choice([2, 2, 3, 3, 4, 5, 6, 12])
        add_qty(b, rng, q)
        b.add(" ")
        b.add(pluralize(food), "FOOD")
    elif r < 0.70:                                           # 2 cups of rice / 200g chicken
        unit, qs = rng.choice(units)
        q = rng.choice(qs)
        if unit in SIZE:
            if rng.random() < 0.5:
                b.add("a ")
            else:
                add_qty(b, rng, q)
                b.add(" ")
        else:
            add_qty(b, rng, q)
            b.add(" ")
        add_unit(b, rng, unit, plural=q > 1)
        b.add(" ")
        b.add(food, "FOOD")
    elif r < 0.80:                                           # a cup of coffee
        unit, _ = rng.choice(units)
        if unit in SIZE:
            b.add("a ")
            add_unit(b, rng, unit)
        else:
            b.add("a " if not unit[0] in "aeiou" else "an ")
            add_unit(b, rng, unit)
            if not b.text.endswith(" of"):
                b.add(" of")
        b.add(" ")
        b.add(food, "FOOD")
    elif r < 0.86:                                           # chicken (150 g) / chicken, 150g
        unit, qs = rng.choice([u for u in units if u[0] not in SIZE] or units)
        b.add(food, "FOOD")
        b.add(rng.choice([" (", ", ", " - ", " "]))
        q = rng.choice(qs)
        add_qty(b, rng, q)
        b.add(" ")
        add_unit(b, rng, unit, plural=q > 1)
        if b.text.endswith(" of"):
            b.text = b.text[:-3]
        if "(" in b.text[-12:] and ")" not in b.text[-12:]:
            b.add(")")
    elif r < 0.91 and dishes:                                # 3-egg omelette
        ingredient = rng.choice(["egg", "cheese", "veggie", "chicken", "turkey", "bean", "mushroom"])
        if rng.random() < 0.6:
            b.add("a ")
        add_qty(b, rng, rng.choice([2, 3, 4]))
        b.add("-")
        b.add(ingredient, "FOOD")
        b.add(" ")
        b.add(rng.choice(dishes), "FOOD")
    elif r < 0.95 and category in ("protein", "bread", "dish", "sweet", "fruit"):  # 2 bacon strips / 1 toast
        q = rng.choice([1, 2, 3, 4])
        add_qty(b, rng, q)
        b.add(" ")
        b.add(food, "FOOD")
        if rng.random() < 0.6:
            b.add(" ")
            b.add(rng.choice(["strips", "slices", "pieces"] if q > 1 else ["strip", "slice", "piece"]), "UNIT")
    else:                                                    # half a banana / a large apple
        if rng.random() < 0.5:
            b.add("half", "QTY")
            b.add(" a ")
        else:
            b.add("a ")
            add_unit(b, rng, rng.choice(["large", "medium", "small"]))
            b.add(" ")
        b.add(food, "FOOD")


def build_vocab(unseen: set[str]):
    vocab: dict[str, list[str]] = {}
    for text, canonical in lexicon.all_surface_forms():
        cat = lexicon.foods()[canonical].category
        vocab.setdefault(cat, []).append(text)
    removed = 0
    for cat, names in EXTRA_FOODS.items():
        keep = [n for n in names if lexicon.normalize(n) not in unseen and lexicon._singular(lexicon.normalize(n)) not in unseen]
        removed += len(names) - len(keep)
        vocab.setdefault(cat, []).extend(keep)
    return {c: sorted(set(v)) for c, v in vocab.items()}, removed


def unseen_test_foods() -> set[str]:
    """Test-set foods that aren't in foods.json. These must never appear in training data."""
    unseen = set()
    for line in (HERE / "test_set.txt").read_text(encoding="utf-8").splitlines():
        for m in re.finditer(r"\[([^\]|]+)\|FOOD\]", line):
            if lexicon.find_food(m.group(1)) is None:
                norm = lexicon.normalize(m.group(1))
                unseen.update({norm, lexicon._singular(norm)})
    return unseen


def negative_text(rng) -> str:
    while True:
        text = rng.choice(NEG_SUBJECTS) + rng.choice(NEG_ACTIONS) + rng.choice(NEG_TAILS)
        if text.lower().strip(". ") not in EXCLUDE_NEGATIVES:
            return text


def make_docs(nlp, rng, n, vocab, cats):
    docs, skipped = [], 0
    dishes = vocab.get("dish", [])
    while len(docs) < n:
        if rng.random() < 0.12:                                   # no food at all
            text = negative_text(rng)
            text = text.lower() if rng.random() < 0.4 else text[:1].upper() + text[1:]
            docs.append(nlp.make_doc(text))
            continue
        k = rng.choices([1, 2, 3, 4], weights=[30, 35, 23, 12])[0]
        b = Builder()
        if rng.random() < 0.1:
            neg = rng.choice(NEG_ACTIONS)
            frame = rng.choice(CONTEXT_FRAMES).replace("{neg_bare}", neg).replace("{neg}", rng.choice(NEG_SUBJECTS[:3]) + neg)
        else:
            frame = rng.choice(FRAMES)
        before, _, after = frame.partition("{items}")
        b.add(before.replace("{meal}", rng.choice(MEALS)))
        for i in range(k):
            if i:
                j = rng.choices([j for j, _ in JOINERS], weights=[w for _, w in JOINERS])[0]
                b.add(j if not (i == k - 1 and j == ", ") else rng.choice([" and ", ", "]))
            cat = rng.choice(cats)
            add_item(b, rng, rng.choice(vocab[cat]), cat, dishes)
        b.add(after.replace("{meal}", rng.choice(MEALS)))
        text, spans = b.text, b.spans
        style = rng.random()
        if style < 0.35:
            text = text.lower()
        elif style < 0.45:
            text = text[:1].upper() + text[1:]
        # prepare_text must not move characters for these generated sentences
        if prepare_text(text) != text:
            skipped += 1
            continue
        doc = nlp.make_doc(text)
        ents = [doc.char_span(s, e, label=l, alignment_mode="strict") for s, e, l in spans]
        if any(x is None for x in ents):
            skipped += 1
            continue
        doc.ents = ents
        docs.append(doc)
    return docs, skipped


def main():
    rng = random.Random(SEED)
    nlp = spacy.blank("en")
    unseen = unseen_test_foods()
    vocab, removed = build_vocab(unseen)

    # Hold out 15% of foods per category for the dev set.
    train_vocab, dev_vocab = {}, {}
    for cat, names in vocab.items():
        names = names[:]
        rng.shuffle(names)
        cut = max(1, int(len(names) * 0.15))
        dev_vocab[cat], train_vocab[cat] = names[:cut], names[cut:]
    cats = sorted(c for c in vocab if train_vocab[c])
    # categories weighted by size so big ones (dishes) appear more
    weighted = [c for c in cats for _ in range(max(1, len(vocab[c]) // 10))]

    train, s1 = make_docs(nlp, rng, N_TRAIN, train_vocab, weighted)
    dev, s2 = make_docs(nlp, rng, N_DEV, dev_vocab, weighted)

    leaked = {lexicon.normalize(e.text) for d in train for e in d.ents if e.label_ == "FOOD"} & unseen
    assert not leaked, f"test-set foods leaked into training data: {sorted(leaked)[:10]}"

    out = HERE / "corpus"
    out.mkdir(exist_ok=True)
    DocBin(docs=train).to_disk(out / "train.spacy")
    DocBin(docs=dev).to_disk(out / "dev.spacy")
    n_foods = sum(len(v) for v in vocab.values())
    print(f"vocab: {n_foods} food names ({removed} extra names removed because they're unseen test-set foods)")
    print(f"test set: {len(unseen)} unseen food forms kept out of training")
    print(f"train: {len(train)} sentences ({s1} skipped)  dev: {len(dev)} sentences with held-out foods ({s2} skipped)")
    for d in train[:8]:
        print("  ", " ".join(f"[{t.text}|{t.ent_type_}]" if t.ent_type_ else t.text for t in d))


if __name__ == "__main__":
    main()
