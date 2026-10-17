# UX changelog

Each entry names the change and the problem it fixes (numbers refer to [`audit.md`](audit.md)). Measured effects are in
[`metrics-comparison.md`](metrics-comparison.md); this file does not claim effects that were not measured.

## Layout (audit 1, 2, 10, 12)

- **Search is the first element of Today.** Goal, macros and water moved below or to the side. *Fixes 1.*
- **Compact header replaces the hero banner**; the Streamlit toolbar is minimal (`toolbarMode = "minimal"`). *Fixes 2.*
- **Four tabs with short labels** (Today, Insights, History, Profile) so all fit at 375 px. *Fixes 2 (clipped History tab).*
- **One slim summary** under the search: kcal vs goal with a bar, protein/carbs/fat vs goals, water. The old goal card, macro mini-bars
  and water card are condensed into it and into a side column. *Fixes 1.*
- **Two columns on desktop** (result and log on the left, macros, water and exercise on the right); a single centered column on phones.
  `layout="wide"` with a 1,180 px maximum content width. *Fixes 1, 12.*
- **Water and Exercise are collapsible** sections. *Fixes 12.*

## Search (audit 14, 20)

- **`st.form`: Enter submits.** *Fixes 14.*
- **Focus on load on desktop** (mouse/keyboard devices only, so phones do not get an unrequested on-screen keyboard).
- **Recent foods and ★ favorites are one-tap chips**; the duplicate recents list in Profile was removed. *Fixes 20.*
- **Meal defaults to the time of day** (browser time zone via `st.context.timezone`, falling back to server time).
- **Clear loading state and friendly errors**: spinner text, a longer note on the first lookup, plain-language messages for rate limits,
  timeouts, unreachable services and "no match". Rate limits were previously reported as "No results".

## Results (audit 3, 4, 5, 10)

- **Ingredient breakdown table**: ingredient, amount, kcal, source badge, match-confidence badge; editable amount, remove per ingredient.
  CalorieNinjas items are no longer merged into a single row. *Fixes 3.*
- **Numbers formatted sensibly** (`200 g`, `1,240 kcal`, not `416.00`).
- **Macro bar rebuilt as accessible HTML**: the legend order is the bar order (carbs, protein, fat), segments under 12% omit the in-bar label,
  and a text list beside the bar always gives each share and grams. *Fixes 5.*
- **Fix-the-match**: "Not right? Pick another match" with the five best USDA candidates; opens automatically for low-confidence matches.
  The choice replaces the item and is logged (`match_choice` table) as a labelled correction for future evaluation. *Fixes 4.*
  On the USDA path the alternatives come from the same search, with no extra API call; on the CalorieNinjas path they are fetched on demand.
- **Confidence badges are scorer hints, not probabilities** (the `high` cut-off is a display choice, documented in `lookup.py`).
  CalorieNinjas items show "NLP-parsed" because that API reports no confidence.

## Persistence and history (audit 8, 13)

- **SQLite persistence** (`data/state.sqlite`, gitignored) for the log, profile, goals, water, exercise, favorites and recents.
  State is keyed by a random id in the URL (`?u=...`), so a refresh or bookmark restores it and users on one server do not see each other's data.
  Limitations (no accounts, ephemeral disk on some hosts) are stated in the README and the Profile tab. *Fixes 8.*
- **Daily snapshots are saved automatically** on every change; the manual "Save Today's Summary" button is gone.
- **Undo** after adding or removing food; per-item edit/remove (`Edit or remove an item`) replaces the all-or-nothing "Clear Log". *Fixes 13.*

## Onboarding and empty states (audit 6, 7)

- **Optional 3-step setup** (goal, body stats, done) with **no hidden defaults**: sex, age, height, weight and activity start empty.
  Skipping gives no calorie goal; the UI shows intake without a target. *Fixes 7.*
- **Suggested goals are explained** (maintenance +/- a stated adjustment; 20/50/30 macro split) and editable.
- **"Load a sample week"** (clearly marked, removable) so Insights and History are meaningful immediately; real empty states explain what to do. *Fixes 6.*
- **Metric/imperial toggle** for body stats (food amounts remain in grams).

## Performance (audit 9)

- **`st.fragment`**: each tab is a fragment; water, exercise, chips, amount edits, match swaps and favorites rerun only the Today fragment.
  Changes other tabs must show (add/remove/undo of food) still do a full rerun. *Fixes 9.*
- **History table and Insights tips refresh themselves every 5 s** (small fragments) so water logged in Today appears without a reload.
- **USDA's three typed searches run in parallel** (the app path), and USDA's intermittent 400s are retried; see "Bugs found" below.
- **`st.cache_data` on lookups** (one hour) and a counter of API calls made vs served from cache.
- **Cold start**: a friendly note on the first lookup. The hosting platform's own wake-up page cannot be changed from the app.

## Accessibility and polish (audit 16, 17, 18, 19)

- **Okabe-Ito colour-blind-safe palette** with text labels and values beside every bar; patterns on the comparison chart.
- **Body text at least 14 px**; captions use a dark grey (`#3b4a3f`, 9.4:1 on white) instead of `#888`/`#999` (3.5:1 and 2.8:1, below the 4.5:1 threshold). *Fixes 17.*
- **Visible keyboard focus** (`:focus-visible` outline) on every control.
- **No `data-testid` CSS**; colours come from `.streamlit/config.toml`, the stylesheet uses generic selectors and its own `np-*` classes. *Fixes 16.*
- **Semantic HTML tables** with captions and `scope`, and `role="progressbar"`/`role="img"` with labels, instead of canvas-only grids.
- **Google Fonts import removed** (no third-party render-blocking request). *Fixes 18.*
- **Everything shown from APIs is HTML-escaped.** *Fixes 19.*
- **"How matching works"** note and a **data sources / not medical advice** footer.

## Bugs found while measuring (not in the original audit)

- **USDA returns an intermittent HTTP 400 for `dataType=Survey (FNDDS)`** (4 of 10 identical calls in a probe; 0 of 20 for the other two data types).
  The original app swallowed it, silently dropping that third of its candidate pool. Now retried up to 4 times and counted
  (`benchmark/results.md`, section 6, shows what still fails after retries).
- **Expanders collapsed after every tap** when their label contained a live number (Streamlit treats a changed label as a new element).
  Found by the water-tap measurement; labels are now static and the live values sit in the summary strip.
- **The USDA fallback path was slow because its three searches ran one after another**; they now run concurrently.

- **"Pick another match" closed itself when you chose an option** after any earlier add (Streamlit remounts the fragment on a full rerun and an
  expander inside it forgets it was open). Found by the end-to-end test; the control is now a toggle whose state lives in `session_state`.
- **The USDA fallback logged "1 banana" as 1 g.** Worse, its unit pattern had no word boundary, so it also corrupted food names:
  `"1 large egg"` searched for "arge egg", `"100 grams chicken"` for "rams chicken", `"1 lemon"` for "emon". Tablespoons, teaspoons,
  ounces, liters and "1 1/2 cups" were not recognised. The parser now uses word boundaries and the full set of unit spellings
  (`parse_amount` in `matching.py`). A bare count, a piece or a slice has no known weight, so the app shows 100 g (the basis USDA values are
  listed for), warns "I can't tell how much ... weighs, so I haven't guessed", and keeps **Add disabled until you type a weight or tap "Keep 100 g"**.
  The meal benchmark excludes such meals from the USDA path instead of scoring an invented weight.

- **A USDA outage looked like "No match".** If every USDA search was refused after retries, the app told you your food had no match.
  It now says the nutrition database could not be reached (a real transient outage during testing showed this working), while a
  genuinely empty search still says "No match".
- **`fl oz` was treated as a weight ounce** (28.35 g); it is now a volume (29.57 g, flagged approximate).
- **The USDA fallback never split a multi-food phrase.** "white rice and carrots" was searched as one food. If the whole-phrase match
  does not explain every content word, each part is now looked up on its own ("macaroni and cheese" stays whole because USDA has that dish).
- **Cup, spoon and unstated amounts ignored the food's real serving sizes.** Cups, tablespoons and teaspoons now use the matched food's own
  USDA portion (a cup of cooked white rice is 174 g, not water's 240 g), falling back to the flagged water approximation when USDA has none.
  For "1 banana" or "2 eggs" the app offers that food's USDA serving sizes to choose from, besides typing a weight. Portion data is fetched
  only when needed and cached; responses of up to 845 KB are slimmed to the few fields used.
- **The "High / Medium / Low match" badge overstated what it knows.** It measures how well the food's *name* fits your words, not whether
  it is the right food, and a breaded chicken product showed as "High" for "chicken breast". The badges now say "Name closely matches /
  Partial name match / Weak name match, check it", and the cut-offs are documented as unvalidated.
- **Autofocus arrived up to 1.4 s late and cost layout space.** The helper is mounted earlier and polls every 50 ms: 5 of 10 loads focus
  within 100 ms and the slowest took 944 ms (`metrics-focus.json`). The hidden helper adds about 17 px above the search box (desktop y 137 -> 154).

## Known limitations (not fixed)

- The match badge thresholds and the scorer itself are not yet validated; the accuracy benchmark exists to do that and still needs labels.
  On real data the scorer picked "egg yolk" for "2 large eggs" and a breaded product for "chicken breast".
- Foods USDA has no serving sizes for still fall back to the water-density approximation for cups and spoons (flagged in the UI).
- ml and litre amounts are converted at 1 g per ml (right for water-like liquids, approximate for others).
- Water and the History table can lag the Today tab by up to 5 s.
- Remaining axe findings come from Streamlit's own widgets (disabled number-input stepper buttons, the popover wrapper, the selectbox
  placeholder colour, page landmarks), not from this app's markup.
- Focus-on-load is intentionally desktop-only.
- Food amounts are editable in grams only.
