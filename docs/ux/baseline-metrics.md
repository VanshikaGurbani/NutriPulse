# Baseline metrics (original UI, before any change)

## Original UI

Measured 2026-10-13 16:34 on the real APIs, Chromium via Playwright (Lighthouse via system Chrome).

### Cost of logging a first food (type `2 cups white rice and carrots`, search, add)

| Viewport | Search box in first screen? | Search box y (px) | Clicks | Keystrokes | Scroll gestures |
|---|---|---|---|---|---|
| 375 px | no | 1179 | 3 | 29 | 3 |
| 1280 px | no | 786 | 3 | 29 | 2 |

Counts were identical across 3 runs per viewport. A scroll gesture is one mouse-wheel step of 70% of the viewport height. Clicks and keystrokes are trusted browser events counted inside the page.

### Latency

| Metric | Value | n |
|---|---|---|
| First page load, cold server (375 px) | 2177 ms | 1 |
| Page reload, warm server | 2211 ms | 1 |
| First search on a fresh server (375 px / 1280 px) | 1393 ms / 1391 ms | 1 each |
| Identical search repeated (served from st.cache_data) | 175 ms | 1 |

Single measurements, not distributions; treat differences under about 300 ms as noise. Search latency here is click-to-result-visible, which includes the Streamlit rerun and the CalorieNinjas call.

### Accessibility

- Lighthouse mobile accessibility score: **88** (runs: [88, 88, 88]), Today tab initial state
- axe-core (wcag2a, wcag2aa, best-practice) across the 4 tabs at 375 px: **4 distinct rules violated** (14 rule-per-tab occurrences), 61 violating nodes; occurrences by impact {'critical': 8, 'moderate': 4, 'serious': 2}

| Rule | Impact | Nodes | Tabs | Description |
|---|---|---|---|---|
| `aria-allowed-attr` | critical | 4 | Today, Insights, Profile, History | Elements must only use supported ARIA attributes |
| `button-name` | critical | 24 | Today, Insights, Profile, History | Buttons must have discernible text |
| `color-contrast` | serious | 5 | Insights, History | Elements must meet minimum color contrast ratio thresholds |
| `region` | moderate | 28 | Today, Insights, Profile, History | All page content should be contained by landmarks |
