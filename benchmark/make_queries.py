"""Writes benchmark/queries.csv: the query list and a stratified dev/test split.
Labels (acceptable_fdc_ids) are left EMPTY on purpose: they come from a human labeler."""
import random

from benchmark.common import QUERIES_CSV, SEED, write_csv

EASY = """white rice|banana|apple|broccoli|egg|salmon|milk|cheddar cheese|spinach|carrot|potato|tomato|avocado
almonds|orange|strawberries|bread|butter|olive oil|pasta|beef|pork chop|tofu|lentils|black beans|chickpeas
oats|walnuts|peanut butter|honey|sugar|cucumber|cauliflower|sweet potato|shrimp|tuna|turkey|bacon|mushrooms
onion|blueberries|grapes|watermelon|quinoa|corn""".replace("\n", "|").split("|")

AMBIGUOUS = """oatmeal|chicken breast|coffee|pizza|yogurt|cereal|ice cream|hamburger|sandwich|soup|salad|smoothie
pancakes|waffles|burrito|taco|sushi|noodles|fries|chips|cookie|cake|muffin|bagel|tea|juice|beer|wine|soda
hot dog|granola|hummus|cottage cheese|greek yogurt|protein bar|rice""".replace("\n", "|").split("|")

MULTIWORD = """brown rice cooked|grilled chicken breast|scrambled eggs|boiled egg|fried egg|almond milk|soy milk
whole wheat bread|white bread|cheese pizza|pepperoni pizza|caesar salad|greek salad|tomato soup|chicken noodle soup
beef stew|mashed potatoes|baked potato|french fries|roasted broccoli|steamed broccoli|cooked spinach|raw spinach
baked salmon|grilled salmon|canned tuna|ground beef|beef steak|pork sausage|turkey breast|chicken thigh|chicken wings
fried chicken|macaroni and cheese|spaghetti with meatballs|lasagna|cheese quesadilla|bean burrito|vegetable stir fry
fried rice|pad thai|chicken curry|lentil soup|black bean soup|oatmeal cookie|chocolate cake|apple pie|banana bread
blueberry muffin|peanut butter and jelly sandwich|turkey sandwich|grilled cheese sandwich|avocado toast
greek yogurt plain|low fat milk|cream cheese|orange juice|apple juice""".replace("\n", "|").split("|")


def build():
    rng = random.Random(SEED)
    rows, seen = [], set()
    for category, items in (("easy", EASY), ("ambiguous", AMBIGUOUS), ("multiword", MULTIWORD)):
        items = [q.strip() for q in items if q.strip() and q.strip() not in seen]
        seen.update(items)
        rng.shuffle(items)
        for i, q in enumerate(items):          # alternate within each category -> ~50/50 and stratified
            rows.append({"query": q, "split": "dev" if i % 2 == 0 else "test", "category": category})
    rng.shuffle(rows)
    out = [{"id": f"q{i + 1:03d}", "query": r["query"], "split": r["split"], "acceptable_fdc_ids": "",
            "notes": f"category={r['category']}"} for i, r in enumerate(rows)]
    write_csv(QUERIES_CSV, out, ["id", "query", "split", "acceptable_fdc_ids", "notes"])
    return out


if __name__ == "__main__":
    rows = build()
    dev = sum(r["split"] == "dev" for r in rows)
    print(f"wrote {len(rows)} queries ({dev} dev / {len(rows) - dev} test) to {QUERIES_CSV}")
