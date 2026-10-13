"""Writes benchmark/meals.csv with meal definitions and EMPTY reference columns.

The reference values (kcal, protein, carbs, fat) must come from a citable source for the exact stated
quantities (for example a package nutrition label or a published restaurant nutrition table) and be filled
in by a human together with ref_source. Rows with empty references are skipped by run_meals.py.
"""
from benchmark.common import BENCH, write_csv

MEALS = [
    ["200 g cooked white rice", "150 g grilled chicken breast"],
    ["100 g oatmeal cooked", "1 banana", "15 g honey"],
    ["2 large eggs scrambled", "2 slices whole wheat bread", "10 g butter"],
    ["170 g plain greek yogurt", "30 g almonds", "80 g blueberries"],
    ["150 g baked salmon", "200 g steamed broccoli", "150 g cooked quinoa"],
    ["200 g cooked spaghetti", "100 g marinara sauce", "30 g parmesan cheese"],
    ["1 medium baked potato", "20 g butter", "30 g cheddar cheese"],
    ["120 g firm tofu", "150 g stir fried vegetables", "200 g cooked brown rice"],
    ["2 slices white bread", "30 g peanut butter", "20 g strawberry jam"],
    ["250 ml whole milk", "40 g cornflakes"],
    ["1 medium apple", "30 g cheddar cheese"],
    ["100 g cooked lentils", "150 g cooked white rice", "100 g sauteed spinach"],
    ["150 g cooked ground beef", "2 corn tortillas", "30 g shredded cheddar cheese"],
    ["200 g canned chickpeas", "100 g cucumber", "100 g tomato", "15 g olive oil"],
    ["1 cup cooked oatmeal", "1 tbsp peanut butter"],
    ["150 g turkey breast", "2 slices whole wheat bread", "1 tbsp mayonnaise"],
    ["200 g cooked pasta", "150 g grilled shrimp", "10 g olive oil"],
    ["2 pancakes", "2 tbsp maple syrup", "10 g butter"],
    ["1 cup cooked black beans", "1 cup cooked white rice"],
    ["100 g cottage cheese", "100 g pineapple"],
    ["150 g sweet potato baked", "100 g black beans"],
    ["1 hamburger patty cooked", "1 hamburger bun", "1 slice cheddar cheese"],
    ["200 g cooked chicken thigh", "200 g mashed potatoes"],
    ["1 cup cooked brown rice", "100 g cooked chicken breast", "100 g broccoli"],
    ["2 tbsp hummus", "100 g carrot sticks", "1 whole wheat pita"],
    ["1 cup tomato soup", "1 slice white bread"],
    ["1 cup chicken noodle soup", "5 saltine crackers"],
    ["1 slice cheese pizza", "1 cup green salad", "1 tbsp ranch dressing"],
    ["200 g cooked white rice", "100 g cooked pork chop"],
    ["1 cup cooked quinoa", "100 g chickpeas", "50 g avocado"],
    ["2 hard boiled eggs", "1 medium banana"],
    ["30 g granola", "150 g plain yogurt", "100 g strawberries"],
    ["100 g tuna canned in water", "2 slices whole wheat bread", "1 tbsp mayonnaise"],
    ["100 g cooked salmon", "150 g cooked asparagus", "100 g cooked white rice"],
    ["1 cup cooked macaroni", "50 g cheddar cheese"],
    ["1 medium orange", "28 g almonds"],
    ["1 cup skim milk", "1 medium banana", "1 tbsp peanut butter"],
    ["150 g beef steak cooked", "150 g baked potato"],
    ["1 cup cooked lentil soup", "1 whole wheat roll"],
    ["100 g cooked turkey", "100 g stuffing", "50 g cranberry sauce"],
    ["2 slices bacon cooked", "2 eggs fried", "1 slice white toast"],
    ["1 cup cooked pasta", "1 cup tomato sauce", "100 g cooked ground turkey"],
    ["1 cup white rice cooked", "1 cup cooked chickpeas", "1 tbsp olive oil"],
    ["200 g watermelon", "30 g feta cheese"],
    ["1 slice banana bread", "1 cup coffee with 2 tbsp whole milk"],
    ["1 bagel", "30 g cream cheese"],
    ["150 g cooked cod", "150 g steamed green beans", "100 g cooked white rice"],
    ["1 cup cooked oatmeal", "1 medium apple", "10 g walnuts"],
]
FIELDS = ["id", "meal_text", "ingredients", "ref_kcal", "ref_protein_g", "ref_carbs_g", "ref_fat_g", "ref_source", "ref_source_note"]

if __name__ == "__main__":
    rows = [{"id": f"m{i + 1:02d}", "meal_text": ", ".join(parts), "ingredients": "|".join(parts),
             "ref_kcal": "", "ref_protein_g": "", "ref_carbs_g": "", "ref_fat_g": "", "ref_source": "", "ref_source_note": ""}
            for i, parts in enumerate(MEALS)]
    write_csv(BENCH / "meals.csv", rows, FIELDS)
    print(f"wrote {len(rows)} meals to benchmark/meals.csv (reference columns empty)")
