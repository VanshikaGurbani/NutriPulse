"""Turns docs/ux/metrics-*.json into markdown. `before` writes baseline-metrics.md; `compare` writes metrics-comparison.md."""
import json
import sys
from pathlib import Path

D = Path(__file__).resolve().parents[2] / "docs/ux"


def load(v):
    return json.loads((D / f"metrics-{v}.json").read_text(encoding="utf-8"))


def row(m, vp):
    runs = m["interaction"][vp]
    first = runs[0]
    return {"clicks": first["clicks"], "keys": first["keystrokes"], "scroll": first["scroll_gestures"],
            "in_view": first["search_in_first_screen"], "y": first["search_box_y_px"], "cold": first["search_ms_cold"],
            "deterministic": len({(r["clicks"], r["keystrokes"], r["scroll_gestures"]) for r in runs}) == 1, "n": len(runs)}


def axe_lines(m):
    agg = {}
    for tab, vs in m["axe"]["per_tab"].items():
        for v in vs:
            a = agg.setdefault(v["id"], {"impact": v["impact"], "nodes": 0, "help": v["help"], "tabs": []})
            a["nodes"] += v["nodes"]
            a["tabs"].append(tab)
    return ["| Rule | Impact | Nodes | Tabs | Description |", "|---|---|---|---|---|"] + [
        f"| `{k}` | {a['impact']} | {a['nodes']} | {', '.join(a['tabs'])} | {a['help']} |"
        for k, a in sorted(agg.items(), key=lambda kv: (kv[1]["impact"] != "critical", kv[1]["impact"] != "serious", kv[0]))]


def distinct_rules(m):
    return {v["id"] for vs in m["axe"]["per_tab"].values() for v in vs}


def metrics_block(m, title):
    L = [f"## {title}", "", f"Measured {m['date']} on the real APIs, Chromium via Playwright (Lighthouse via system Chrome).", "",
         "### Cost of logging a first food (type `2 cups white rice and carrots`, search, add)", "",
         "| Viewport | Search box in first screen? | Search box y (px) | Clicks | Keystrokes | Scroll gestures |", "|---|---|---|---|---|---|"]
    for vp in ("375", "1280"):
        r = row(m, vp)
        L.append(f"| {vp} px | {'yes' if r['in_view'] else 'no'} | {r['y']} | {r['clicks']} | {r['keys']} | {r['scroll']} |")
        assert r["deterministic"]
    L += ["", f"Counts were identical across {row(m, '375')['n']} runs per viewport. A scroll gesture is one mouse-wheel step of 70% of the viewport height. "
          "Clicks and keystrokes are trusted browser events counted inside the page.", "",
          "### Latency", "", "| Metric | Value | n |", "|---|---|---|",
          f"| First page load, cold server (375 px) | {m['latency']['load_cold_ms']} ms | 1 |",
          f"| Page reload, warm server | {m['latency']['load_warm_ms']} ms | 1 |",
          f"| First search on a fresh server (375 px / 1280 px) | {row(m, '375')['cold']} ms / {row(m, '1280')['cold']} ms | 1 each |",
          f"| Identical search repeated (served from st.cache_data) | {m['latency']['repeat_search_ms']} ms | 1 |", "",
          "Single measurements, not distributions; treat differences under about 300 ms as noise. "
          "Search latency here is click-to-result-visible, which includes the Streamlit rerun and the CalorieNinjas call.", "",
          "### Accessibility", "",
          f"- Lighthouse mobile accessibility score: **{m['lighthouse']['median']:.0f}** (runs: {m['lighthouse']['scores']}), Today tab initial state",
          f"- axe-core (wcag2a, wcag2aa, best-practice) across the 4 tabs at 375 px: **{len(distinct_rules(m))} distinct rules violated** "
          f"({m['axe']['violation_rules_total']} rule-per-tab occurrences), {m['axe']['violating_nodes_total']} violating nodes; "
          f"occurrences by impact {m['axe']['rules_by_impact']}", ""] + axe_lines(m) + [""]
    return L


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "before":
        (D / "baseline-metrics.md").write_text("\n".join(["# Baseline metrics (original UI, before any change)", ""] + metrics_block(load("before"), "Original UI")), encoding="utf-8")
    else:
        b, a = load("before"), load("after")
        L = ["# Before vs after", ""]
        L += ["| Metric | Before | After |", "|---|---|---|"]
        for vp in ("375", "1280"):
            rb, ra = row(b, vp), row(a, vp)
            L += [f"| {vp} px: search box in first screen | {'yes' if rb['in_view'] else 'no'} (y={rb['y']}) | {'yes' if ra['in_view'] else 'no'} (y={ra['y']}) |",
                  f"| {vp} px: clicks to log a first food | {rb['clicks']} | {ra['clicks']} |",
                  f"| {vp} px: keystrokes | {rb['keys']} | {ra['keys']} |",
                  f"| {vp} px: scroll gestures | {rb['scroll']} | {ra['scroll']} |",
                  f"| {vp} px: first search on fresh server | {rb['cold']} ms | {ra['cold']} ms |"]
        L += [f"| First load, cold | {b['latency']['load_cold_ms']} ms | {a['latency']['load_cold_ms']} ms |",
              f"| Repeat search (cache) | {b['latency']['repeat_search_ms']} ms | {a['latency']['repeat_search_ms']} ms |",
              f"| Lighthouse mobile accessibility | {b['lighthouse']['median']:.0f} | {a['lighthouse']['median']:.0f} |",
              f"| axe distinct rules violated (4 tabs, 375 px) | {len(distinct_rules(b))} | {len(distinct_rules(a))} |",
              f"| axe violating nodes | {b['axe']['violating_nodes_total']} | {a['axe']['violating_nodes_total']} |", ""]
        L += metrics_block(a, "After")
        (D / "metrics-comparison.md").write_text("\n".join(L), encoding="utf-8")
