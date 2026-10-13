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

## Known limitations (not fixed)

- On the USDA fallback path, unit-less quantities are read as grams (`"1 banana"` is 1 g, `"2 eggs"` is 2 g). The CalorieNinjas path handles them.
- Water and the History table can lag the Today tab by up to 5 s.
- Remaining axe findings come from Streamlit's own widgets (disabled number-input stepper buttons, the popover wrapper, the selectbox
  placeholder colour, page landmarks), not from this app's markup.
- Focus-on-load is intentionally desktop-only.
- Food amounts are editable in grams only.
