# Amount handling on real USDA data (fallback path)

Generated 2026-10-13 23:39 by `tools/ux/check_amounts.py`. Seven phrases, USDA data as of that date, CalorieNinjas disabled. Illustrates behaviour; it is not an accuracy measurement. The matched food is the scorer's choice and can be wrong (see the benchmark).

| Phrase | Matched food | Amount used | How the amount was decided | USDA serving sizes found |
|---|---|---|---|---|
| 1 cup cooked white rice | Rice, white, cooked, glutinous | 174 g | Using USDA's serving size for this food: “1 cup, cooked”. | - |
| 2 cups white rice and carrots | Rice, white, with carrots and dark green vegetables, fat added | 344 g | Using USDA's serving size for this food: “1 cup”. | - |
| 3 tbsp peanut butter | Peanut butter | 48 g | Using USDA's serving size for this food: “1 tablespoon”. | - |
| 1 banana | Banana, raw | 100 g | NOT stated: 100 g placeholder, must be confirmed | 1 cup, mashed, 1 banana, 1 cup |
| 2 large eggs | Eggs, Grade A, Large, egg yolk | 100 g | NOT stated: 100 g placeholder, must be confirmed | egg, yolk |
| macaroni and cheese | Macaroni and Cheese, canned entree | 100 g | NOT stated: 100 g placeholder, must be confirmed | serving |
| 100 g chicken breast | Chicken breast tenders, breaded, uncooked | 100 g | stated weight | - |

Live API calls: 8; served from cache: 20; retried 400s: 1; failed after retries: 0.
