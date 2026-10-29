"""Food logging: turn a meal description into ingredients with nutrition from USDA FoodData Central.

parser.py    text -> ingredients (spaCy model trained in backend/ml/food_ner)
lexicon.py   common foods pinned to FDC ids, plus dish recipes
fdc.py       FoodData Central API client and result ranking
units.py     quantity and unit parsing
portions.py  quantity + unit -> grams using FDC portions
service.py   the whole pipeline, with Supabase caching and storage

Nutrition values always come from FoodData Central, never from the parser.
"""
