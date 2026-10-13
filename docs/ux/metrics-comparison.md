# Before vs after

| Metric | Before | After |
|---|---|---|
| 375 px: search box in first screen | no (y=1179) | yes (y=167) |
| 375 px: clicks to log a first food | 3 | 2 |
| 375 px: keystrokes | 29 | 30 |
| 375 px: scroll gestures | 3 | 2 |
| 375 px: first search on fresh server | 1393 ms | 1363 ms |
| 1280 px: search box in first screen | no (y=786) | yes (y=137) |
| 1280 px: clicks to log a first food | 3 | 1 |
| 1280 px: keystrokes | 29 | 30 |
| 1280 px: scroll gestures | 2 | 1 |
| 1280 px: first search on fresh server | 1391 ms | 875 ms |
| First load, cold | 2177 ms | 2181 ms |
| Repeat search (cache) | 175 ms | 169 ms |
| Lighthouse mobile accessibility | 88 | 100 |
| axe distinct rules violated (4 tabs, 375 px) | 4 | 4 |
| axe violating nodes | 61 | 49 |

## After

Measured 2026-10-13 16:58 on the real APIs, Chromium via Playwright (Lighthouse via system Chrome).

### Cost of logging a first food (type `2 cups white rice and carrots`, search, add)

| Viewport | Search box in first screen? | Search box y (px) | Clicks | Keystrokes | Scroll gestures |
|---|---|---|---|---|---|
| 375 px | yes | 167 | 2 | 30 | 2 |
| 1280 px | yes | 137 | 1 | 30 | 1 |

Counts were identical across 3 runs per viewport. A scroll gesture is one mouse-wheel step of 70% of the viewport height. Clicks and keystrokes are trusted browser events counted inside the page.

### Latency

| Metric | Value | n |
|---|---|---|
| First page load, cold server (375 px) | 2181 ms | 1 |
| Page reload, warm server | 1020 ms | 1 |
| First search on a fresh server (375 px / 1280 px) | 1363 ms / 875 ms | 1 each |
| Identical search repeated (served from st.cache_data) | 169 ms | 1 |

Single measurements, not distributions; treat differences under about 300 ms as noise. Search latency here is click-to-result-visible, which includes the Streamlit rerun and the CalorieNinjas call.

### Accessibility

- Lighthouse mobile accessibility score: **100** (runs: [100, 100, 100]), Today tab initial state
- axe-core (wcag2a, wcag2aa, best-practice) across the 4 tabs at 375 px: **4 distinct rules violated** (8 rule-per-tab occurrences), 49 violating nodes; occurrences by impact {'serious': 2, 'moderate': 4, 'critical': 2}

| Rule | Impact | Nodes | Tabs | Description |
|---|---|---|---|---|
| `aria-allowed-attr` | critical | 1 | Profile | Elements must only use supported ARIA attributes |
| `button-name` | critical | 18 | Profile | Buttons must have discernible text |
| `color-contrast` | serious | 2 | Today, Profile | Elements must meet minimum color contrast ratio thresholds |
| `region` | moderate | 28 | Today, Insights, Profile, History | All page content should be contained by landmarks |
