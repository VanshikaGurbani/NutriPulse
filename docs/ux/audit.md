# UX audit (baseline, before any UI change)

Screenshots: `docs/ux/before/` (375x812 and 1280x800; `-fold` is the first screen, `-full` the whole tab).
Captured with `python -m tools.ux.capture docs/ux/before` against a **local mock API** (layout only). Each item below
was checked against the code in `nutrition_tracker.py` (function/section named) and, where visible, a screenshot.

## Your nine findings

| # | Finding | Verified? | Evidence |
|---|---------|-----------|----------|
| 1 | Primary action "Search a food" is below the fold | **Confirmed** | Today tab order is Calorie Goal, Water, Search, Result, Log, Exercise. At 375x812 the first screen shows only the banner, tabs and the calorie goal (`today-empty-fold-375.png`); Search is reached after scrolling past goal, macros and water. |
| 2 | Hero banner takes ~1/3 of the first mobile screen; History tab clips | **Confirmed, number corrected** | Measured from the screenshot: the banner is about 203 px of 812 (about 25%), and with the Streamlit header gap, content starts at about y=355 (44% of the screen). Of the 4 tabs only 3 fit at 375 px; History is off-screen and the tab bar scrolls horizontally (`history-saved-fold-375.png` shows the bar scrolled). |
| 3 | Multi-ingredient queries are merged into one result | **Confirmed** | `apis.search_food_nlp` sums all CalorieNinjas items into one row, "White Rice + Carrots", serving 416 g, per-100 g values (`today-result-full-375.png`). The item breakdown the API returned is discarded. |
| 4 | Low-confidence matches have no way to pick another match | **Confirmed** | `low_confidence` only shows a warning telling the user to rephrase. `best_match` keeps only the top candidate; the other candidates are thrown away. |
| 5 | Macro bar legend order differs from bar order; small segments unreadable | **Confirmed in code, legend order not yet visually checked** | `macro_bar_fig` adds traces Carbs, Protein, Fat and anchors the legend right (`xanchor="right"`); the in-bar text is a fixed 12 px, so a segment of a few percent cannot fit its label. I will check the rendered legend order in the after-screenshots. |
| 6 | Insights and History show only an empty info box | **Confirmed** | Insights with no log renders one `st.info` (the Food Comparison card is the only other content). History shows a caption and a button. |
| 7 | Profile is silently prefilled with example values that drive TDEE | **Confirmed** | `st.session_state.profile` defaults: Female, 25, 65 kg, 165 cm, moderate activity. The TDEE shown on first open is computed from these. Macro goals default to 50/300/65/28 g, also silent. |
| 8 | State lives in `st.session_state`, so a refresh loses the log | **Confirmed** | Log, water, exercise, profile, goals, history and recent foods are all session-only. History only exists if the user presses the manual save button, and is lost on refresh anyway. |
| 9 | Every water/meal click calls `st.rerun()` | **Confirmed** | Water buttons, recent-food chips, Clear Log, Clear Exercise Log and the Profile "Search" buttons all call `st.rerun()`, a full-script rerun. Nothing uses `st.fragment`. |

## Additional problems found

| # | Problem | Evidence |
|---|---------|----------|
| 10 | Macro cards in the result are cut off at 375 px: the 5-column grid overflows and Fiber is clipped | `today-result-full-375.png` |
| 11 | Unit-less quantities silently become grams on the USDA fallback path: `parse_serving("1 banana")` returns 1 g (verified: `parse_serving("1 banana")` gives 1 g, `"2 eggs"` gives 2 g, bare `"banana"` gives 100 g). Pieces ("2 eggs") are not understood. | `nutripulse/matching.py` `parse_serving` |
| 12 | Water row: 5 columns collapse into 5 full-width stacked buttons on mobile, about 300 px of vertical space for one tracker | `today-result-full-375.png` |
| 13 | No per-item delete or edit in the food log; only "Clear Log", with no confirmation and no undo | `Today's Food Log` section |
| 14 | Pressing Enter in the search box does nothing (not a form); the user must find and click "Analyze Food" | `food_input` / `analyze_clicked` |
| 15 | ~~Calorie goal and water goal inputs hide their labels (`label_visibility="collapsed"`)~~ **Retracted after measuring.** Streamlit still exposes the label to assistive tech as an aria-label, and axe reported no missing-label violation on the original UI. It is a visual-only issue (no visible label), not an accessibility failure. | Today tab; axe baseline |
| 16 | Styling relies on `data-testid` selectors (`stVerticalBlockBorderWrapper`, `stTextInput`, `stButton`, `stRadio`, `stTabs`) that Streamlit does not guarantee to keep | CSS block in `nutrition_tracker.py` |
| 17 | Low-contrast text: **confirmed, narrower than first stated.** The baseline axe run found `color-contrast` failures on 5 nodes (Insights and History tabs). Small text sizes (0.72-0.82 rem) and `#888`/`#999` greys are in the code but only those 5 nodes failed the 4.5:1 threshold. | `docs/ux/baseline-metrics.md` |
| 18 | Fonts are loaded from Google at runtime via `@import`, adding a render-blocking third-party request | CSS block |
| 19 | USDA/CalorieNinjas food names are interpolated into `unsafe_allow_html` markup unescaped (low risk, API-sourced, but not safe by construction) | `result-food-name` markdown |
| 20 | Recent foods appear in two places (Today chips and Profile tab list); the Profile tab is the wrong home for them | Tabs 1 and 3 |
| 21 | Thumbs up/down buttons that I added in the feedback phase stack vertically on mobile with large gaps (my own regression; fixed in the layout phase) | `today-result-full-375.png` |

## Baseline measurements

Recorded before any UI change in `docs/ux/baseline-metrics.md` (clicks/keystrokes to log a first food, Lighthouse mobile
accessibility 88, axe 4 distinct rules / 61 nodes, load and search latency).
