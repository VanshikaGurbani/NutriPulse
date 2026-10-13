"""Benchmark: naive USDA top-1 vs the heuristic scorer (and CalorieNinjas calorie agreement).

    python -m benchmark.run_benchmark tune     # DEV split only: tunes scorer weights, writes tuned_weights.json
    python -m benchmark.run_benchmark report   # TEST split only: writes results.md/csv and charts

Rules enforced in code:
  * `tune` loads only split == "dev"; `report` loads only split == "test" (asserted).
  * Queries with no acceptable label are excluded and counted; blank labels abort the run.
  * Live API calls are capped (--max-calls, default 500) and everything is cached in benchmark/cache.
"""
import argparse
import datetime
import json
import subprocess

from benchmark.common import (BENCH, ROOT, SEED, QUERIES_CSV, apis, file_sha, kcal_per_100g, load_queries, matching,
                              parse_ids, setup_cache, stats, write_csv)
from benchmark.make_labeling_sheet import FIELDS as SHEET_FIELDS
from benchmark.make_labeling_sheet import pick_pool
from benchmark.metrics import bootstrap_ci, first_rank, mean, paired_bootstrap_diff, per_query_scores
from nutripulse.matching import ABLATION_GROUPS, DEFAULT_WEIGHTS, _score, query_words, score_terms

TUNED_PATH = BENCH / "tuned_weights.json"
CHART_DIR = BENCH / "charts"
SCALES = [0.0, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
N_BOOT = 1000


# ── data loading ─────────────────────────────────────────────────────────────

def load_items(split):
    """Labelled queries of one split with their candidate pools. Returns (items, excluded_info)."""
    assert split in ("dev", "test")
    rows = load_queries(split)
    unlabeled = [r["id"] for r in rows if "labeled=1" not in r["notes"]]
    if unlabeled:
        raise SystemExit(f"{len(unlabeled)} {split} queries are not labelled yet (first: {unlabeled[0]}). "
                         "Label them via the labeling sheet + benchmark.apply_labels; refusing to report on a partial set.")
    items, no_acceptable = [], []
    for r in rows:
        acc = parse_ids(r["acceptable_fdc_ids"])
        if not acc:
            no_acceptable.append(r["id"])
            continue
        lists = matching.candidate_lists(r["query"])
        pool = [f for lst in lists for f in lst]
        items.append({"id": r["id"], "query": r["query"], "acceptable": acc, "pool": pool,
                      "shown": {f["fdcId"] for f in pick_pool(lists)}, "category": r["notes"]})
    return items, {"n_split": len(rows), "no_acceptable": no_acceptable}


# ── systems: each maps an item to a ranked list of candidate foods ───────────

def rank_naive(item):
    return list(item["pool"])


def rank_scorer(item, weights=None):
    qw = query_words(item["query"])
    return sorted(item["pool"], key=lambda f: -_score(f, qw, weights))   # stable: ties keep API order


def evaluate(items, ranker):
    """Per-query records for one system."""
    out = []
    for it in items:
        ranked = ranker(it)
        ids = [f["fdcId"] for f in ranked]
        rank = first_rank(ids, it["acceptable"])
        t1, t3, rr = per_query_scores(rank)
        top = ranked[0] if ranked else None
        out.append({"id": it["id"], "rank": rank, "top1": t1, "top3": t3, "rr": rr, "pick": top,
                    "unlabeled_pick": bool(top) and top["fdcId"] not in it["shown"]})
    return out


def summarize(records):
    res = {}
    for key in ("top1", "top3", "rr"):
        vals = [r[key] for r in records]
        lo, hi = bootstrap_ci(vals, N_BOOT, SEED)
        res[key] = (mean(vals), lo, hi)
    res["n"] = len(records)
    res["unlabeled_picks"] = sum(r["unlabeled_pick"] for r in records)
    res["pool_miss"] = sum(r["rank"] is None for r in records)
    return res


# ── tuning (dev only) ────────────────────────────────────────────────────────

def objective(items, weights):
    recs = evaluate(items, lambda it: rank_scorer(it, weights))
    return mean([r["top1"] for r in recs]), mean([r["rr"] for r in recs])


def tune_weights(dev_items, passes=3):
    """Coordinate search over per-term scale factors on DEV. Accepts a change only if dev top-1 rises,
    or top-1 ties and dev MRR rises by more than 0.005. Deterministic."""
    w = dict(DEFAULT_WEIGHTS)
    start = objective(dev_items, w)
    for _ in range(passes):
        changed = False
        for term in w:
            best = objective(dev_items, w)
            for s in SCALES:
                cand = dict(w, **{term: DEFAULT_WEIGHTS[term] * s})
                t1, mrr = objective(dev_items, cand)
                if t1 > best[0] or (t1 == best[0] and mrr > best[1] + 0.005):
                    best, w, changed = (t1, mrr), cand, True
        if not changed:
            break
    return w, start, objective(dev_items, w)


def cmd_tune(args):
    items, info = load_items("dev")
    assert all(load_q["split"] == "dev" for load_q in load_queries("dev"))
    if len(items) < 20:
        raise SystemExit(f"only {len(items)} labelled dev queries; label more before tuning")
    w, before, after = tune_weights(items)
    dev_sha = file_sha_of_ids([i["id"] for i in items])
    TUNED_PATH.write_text(json.dumps({
        "weights": w, "tuned_on": "dev", "n_dev": len(items), "dev_ids_sha": dev_sha,
        "dev_top1_before": before[0], "dev_mrr_before": before[1],
        "dev_top1_after": after[0], "dev_mrr_after": after[1]}, indent=2), encoding="utf-8")
    print(f"dev n={len(items)}: top-1 {before[0]:.3f} -> {after[0]:.3f}, MRR {before[1]:.3f} -> {after[1]:.3f}")
    print("weights:", {k: round(v, 3) for k, v in w.items()})
    print("(dev numbers are tuning diagnostics only, never reported as results)")


def file_sha_of_ids(ids):
    import hashlib
    return hashlib.sha256("|".join(sorted(ids)).encode()).hexdigest()[:12]


# ── CalorieNinjas: calorie agreement (different criterion, see results.md) ───

def kcal_agrees(pick_kcal, acceptable_kcals, tol=0.20):
    return any(abs(pick_kcal - a) <= max(tol * a, 5.0) for a in acceptable_kcals)


def agreement_table(items, scorer_recs, naive_recs):
    rows = {"naive": [], "scorer": [], "cn": []}
    cn_covered = 0
    for it, s, n in zip(items, scorer_recs, naive_recs):
        acc_k = [kcal_per_100g(f) for f in it["pool"] if f["fdcId"] in it["acceptable"]]
        if not acc_k:
            continue
        rows["scorer"].append(float(bool(s["pick"]) and kcal_agrees(kcal_per_100g(s["pick"]), acc_k)))
        rows["naive"].append(float(bool(n["pick"]) and kcal_agrees(kcal_per_100g(n["pick"]), acc_k)))
        cn = apis.search_food_nlp(it["query"])
        if cn is not None:
            cn_covered += 1
        rows["cn"].append(float(cn is not None and kcal_agrees(cn["calories"], acc_k)))
    out = {}
    for k, v in rows.items():
        lo, hi = bootstrap_ci(v, N_BOOT, SEED)
        out[k] = (mean(v), lo, hi, len(v))
    out["cn_coverage"] = (cn_covered, len(rows["cn"]))
    return out


# ── error analysis ───────────────────────────────────────────────────────────

def explain_miss(item, rec, naive_rec, weights=None):
    w = weights or DEFAULT_WEIGHTS
    qw = query_words(item["query"])
    ranked = rank_scorer(item, weights)
    ids = [f["fdcId"] for f in ranked]
    best_acc = next((f for f in ranked if f["fdcId"] in item["acceptable"]), None)
    picked = ranked[0]
    if best_acc is None:
        return {"cause": "no acceptable id in the current API results (label/API data drift)", "acc": None}
    tp, ta = score_terms(picked, qw), score_terms(best_acc, qw)
    adv = sorted(((w[k] * (tp[k] - ta[k]), k) for k in w), reverse=True)
    top = [f"{k} ({v:+.1f})" for v, k in adv if abs(v) > 1e-9][:2]
    return {"cause": "picked-vs-acceptable score gap driven by " + (", ".join(top) or "ties/ordering"),
            "acc": best_acc, "acc_rank": ids.index(best_acc["fdcId"]) + 1,
            "gap": _score(picked, qw, weights) - _score(best_acc, qw, weights)}


# ── report ───────────────────────────────────────────────────────────────────

def fmt(m, lo, hi):
    return f"{m * 100:.1f}% [{lo * 100:.1f}, {hi * 100:.1f}]"


def git_head():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def cmd_report(args):
    items, info = load_items("test")
    assert all(q["split"] == "test" for q in load_queries("test"))
    if not items:
        raise SystemExit("no labelled test queries; fill the labeling sheet and run benchmark.apply_labels first")
    tuned = None
    if TUNED_PATH.exists():
        t = json.loads(TUNED_PATH.read_text(encoding="utf-8"))
        dev_ids = [q["id"] for q in load_queries("dev") if q["acceptable_fdc_ids"]]
        if t["dev_ids_sha"] == file_sha_of_ids(dev_ids):
            tuned = t
        else:
            print("WARNING: tuned_weights.json was fit on a different dev set; ignoring it (re-run `tune`).")

    systems = {"Naive USDA top-1 (API order)": lambda it: rank_naive(it),
               "Current scorer (default weights)": lambda it: rank_scorer(it)}
    if tuned:
        systems["Scorer, weights tuned on dev"] = lambda it: rank_scorer(it, tuned["weights"])
    recs = {name: evaluate(items, fn) for name, fn in systems.items()}
    summ = {name: summarize(r) for name, r in recs.items()}
    naive_name, base_name = list(systems)[0], list(systems)[1]

    # paired comparison scorer vs naive
    comps = []
    for name in list(systems)[1:]:
        d1 = paired_bootstrap_diff([r["top1"] for r in recs[name]], [r["top1"] for r in recs[naive_name]], N_BOOT, SEED)
        dm = paired_bootstrap_diff([r["rr"] for r in recs[name]], [r["rr"] for r in recs[naive_name]], N_BOOT, SEED)
        wins = sum(a["rank"] is not None and (b["rank"] is None or a["rank"] < b["rank"])
                   for a, b in zip(recs[name], recs[naive_name]))
        losses = sum(b["rank"] is not None and (a["rank"] is None or b["rank"] < a["rank"])
                     for a, b in zip(recs[name], recs[naive_name]))
        comps.append((name, d1, dm, wins, losses, len(items) - wins - losses))

    # ablation (default weights)
    base_t1 = [r["top1"] for r in recs[base_name]]
    base_rr = [r["rr"] for r in recs[base_name]]
    ablation = []
    for group, terms in ABLATION_GROUPS.items():
        w = dict(DEFAULT_WEIGHTS, **{t: 0.0 for t in terms})
        rr = evaluate(items, lambda it, w=w: rank_scorer(it, w))
        d1 = paired_bootstrap_diff(base_t1, [r["top1"] for r in rr], N_BOOT, SEED)
        dm = paired_bootstrap_diff(base_rr, [r["rr"] for r in rr], N_BOOT, SEED)
        ablation.append((group, mean([r["top1"] for r in rr]), d1, dm))

    agree = agreement_table(items, recs[base_name], recs[naive_name])

    # error analysis: 10 worst scorer misses
    misses = []
    for it, rec, nrec in zip(items, recs[base_name], recs[naive_name]):
        if rec["rank"] != 1:
            ex = explain_miss(it, rec, nrec)
            misses.append((rec["rank"] if rec["rank"] else 10_000, it, rec, nrec, ex))
    misses.sort(key=lambda m: (-m[0], m[1]["id"]))
    worst = misses[:10]

    write_outputs(items, info, systems, summ, comps, ablation, agree, worst, tuned, recs, naive_name, base_name)
    write_unlabeled_sheet(items, recs)
    print(f"wrote benchmark/results.md, results.csv, charts/*.png  (n={len(items)} test queries)")
    print(f"live API calls this run: {stats.api_calls}; served from cache: {stats.cache_hits}")


def verdict(d1):
    mean_d, lo, hi = d1
    if lo > 0:
        return f"The scorer improves top-1 over naive USDA ranking (paired difference {mean_d * 100:+.1f} pts, 95% CI [{lo * 100:+.1f}, {hi * 100:+.1f}] excludes 0)."
    if hi < 0:
        return f"The scorer is WORSE than naive USDA ranking on top-1 (paired difference {mean_d * 100:+.1f} pts, 95% CI [{lo * 100:+.1f}, {hi * 100:+.1f}])."
    return (f"No reliable top-1 difference between the scorer and naive USDA ranking at this sample size "
            f"(paired difference {mean_d * 100:+.1f} pts, 95% CI [{lo * 100:+.1f}, {hi * 100:+.1f}] includes 0).")


def write_outputs(items, info, systems, summ, comps, ablation, agree, worst, tuned, recs, naive_name, base_name):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    CHART_DIR.mkdir(exist_ok=True)
    csv_rows = []
    L = ["# Benchmark results", "",
         f"Generated {datetime.datetime.now():%Y-%m-%d %H:%M} from commit `{git_head()}`. "
         f"**Test split only** (n = {len(items)} labelled queries); weights were tuned on the dev split only.", "",
         f"- `queries.csv` sha: `{file_sha(QUERIES_CSV)}`; split size {info['n_split']}, excluded (no acceptable candidate): {len(info['no_acceptable'])}",
         f"- Bootstrap: {N_BOOT} resamples of queries, 95% percentile CI, seed {SEED}",
         f"- Live API calls during this report: {stats.api_calls}; served from cache: {stats.cache_hits}", "",
         "## 1. Match accuracy (exact acceptable FDC id)", "",
         "| System | Top-1 [95% CI] | Top-3 [95% CI] | MRR [95% CI] | n |", "|---|---|---|---|---|"]
    for name, s in summ.items():
        L.append(f"| {name} | {fmt(*s['top1'])} | {fmt(*s['top3'])} | {s['rr'][0]:.3f} [{s['rr'][1]:.3f}, {s['rr'][2]:.3f}] | {s['n']} |")
        for key, label in (("top1", "top1"), ("top3", "top3"), ("rr", "mrr")):
            csv_rows.append({"section": "accuracy", "system": name, "metric": label, "value": round(s[key][0], 4),
                             "ci_low": round(s[key][1], 4), "ci_high": round(s[key][2], 4), "n": s["n"]})
    L += ["", "### Paired comparison against naive USDA top-1", "",
          "| System | Δ Top-1 (pts) [95% CI] | Δ MRR [95% CI] | wins / losses / ties |", "|---|---|---|---|"]
    for name, d1, dm, w, lo_, t in comps:
        L.append(f"| {name} | {d1[0] * 100:+.1f} [{d1[1] * 100:+.1f}, {d1[2] * 100:+.1f}] | {dm[0]:+.3f} [{dm[1]:+.3f}, {dm[2]:+.3f}] | {w} / {lo_} / {t} |")
        csv_rows.append({"section": "paired_vs_naive", "system": name, "metric": "delta_top1", "value": round(d1[0], 4),
                         "ci_low": round(d1[1], 4), "ci_high": round(d1[2], 4), "n": len(items)})
    L += ["", f"**Reading:** {verdict(comps[0][1])}", ""]
    if tuned:
        L.append(f"Tuned weights were fit on {tuned['n_dev']} dev queries (dev top-1 {tuned['dev_top1_before']:.3f} -> "
                 f"{tuned['dev_top1_after']:.3f}); the test numbers above are the honest out-of-sample result.")
        L.append("")
    L += ["Candidates the system picked that were not on the labeling sheet count as wrong "
          "(unlabeled picks: " + ", ".join(f"{n.split(' (')[0]} {s['unlabeled_picks']}" for n, s in summ.items()) +
          "). `benchmark/unlabeled_picks_sheet.csv` lists them for a blind second labeling pass.", ""]

    L += ["## 2. Calorie agreement (different, weaker criterion)", "",
          "CalorieNinjas returns no FDC ids, so it cannot be scored on exact match. Here a result counts as correct "
          "if its kcal/100 g is within 20% (or 5 kcal) of at least one acceptable USDA item. The same criterion is applied "
          "to the USDA systems so the rows are comparable to each other, but **this is not the same metric as Section 1**.", "",
          "| System | Agreement [95% CI] | n |", "|---|---|---|"]
    for key, label in (("naive", "Naive USDA top-1"), ("scorer", "Current scorer"), ("cn", "CalorieNinjas alone")):
        m, lo, hi, n = agree[key]
        L.append(f"| {label} | {fmt(m, lo, hi)} | {n} |")
        csv_rows.append({"section": "kcal_agreement", "system": label, "metric": "agree_20pct", "value": round(m, 4),
                         "ci_low": round(lo, 4), "ci_high": round(hi, 4), "n": n})
    L += ["", f"CalorieNinjas returned a result for {agree['cn_coverage'][0]} of {agree['cn_coverage'][1]} queries "
          "(misses count as wrong above).", ""]

    L += ["## 3. Ablation (current scorer, test split)", "",
          "Each row removes one term (weight set to 0). Drop = default top-1 minus ablated top-1; positive means the term helps.", "",
          "| Removed term | Top-1 without term | Drop in top-1 (pts) [95% CI] | Drop in MRR |", "|---|---|---|---|"]
    for group, t1, d1, dm in ablation:
        L.append(f"| {group} | {t1 * 100:.1f}% | {d1[0] * 100:+.1f} [{d1[1] * 100:+.1f}, {d1[2] * 100:+.1f}] | {dm[0]:+.3f} |")
        csv_rows.append({"section": "ablation", "system": group, "metric": "top1_drop_pts", "value": round(d1[0] * 100, 2),
                         "ci_low": round(d1[1] * 100, 2), "ci_high": round(d1[2] * 100, 2), "n": len(items)})
    L += ["", "## 4. Ten worst misses of the current scorer (test split)", "",
          "Cause is computed from the score terms (which term gave the wrong pick its largest advantage over the best acceptable "
          "candidate), not hand-written.", "",
          "| Query | Scorer picked | Best acceptable (its rank) | Naive correct? | Cause |", "|---|---|---|---|---|"]
    for _, it, rec, nrec, ex in worst:
        acc = f"{ex['acc'].get('description')} (#{ex['acc_rank']})" if ex["acc"] else "not in current results"
        L.append(f"| {it['query']} | {rec['pick'].get('description', '?') if rec['pick'] else 'none'} | {acc} | "
                 f"{'yes' if nrec['rank'] == 1 else 'no'} | {ex['cause']} |")
    L.append("")
    (BENCH / "results.md").write_text("\n".join(L), encoding="utf-8")
    write_csv(BENCH / "results.csv", csv_rows, ["section", "system", "metric", "value", "ci_low", "ci_high", "n"])

    # charts
    fig, ax = plt.subplots(figsize=(7, 4))
    names = list(summ)
    vals = [summ[n]["top1"][0] * 100 for n in names]
    errs = [[summ[n]["top1"][0] * 100 - summ[n]["top1"][1] * 100 for n in names],
            [summ[n]["top1"][2] * 100 - summ[n]["top1"][0] * 100 for n in names]]
    ax.bar(range(len(names)), vals, yerr=errs, capsize=5, color=["#9e9e9e", "#2d6a4f", "#1976d2"][:len(names)])
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([n.replace(" (", "\n(") for n in names], fontsize=8)
    ax.set_ylabel("Top-1 accuracy (%)")
    ax.set_title(f"Top-1 accuracy by system, test split (n={len(items)}), 95% bootstrap CI")
    ax.set_ylim(0, 105)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "accuracy_by_system.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    g = [a[0] for a in ablation]
    d = [a[2][0] * 100 for a in ablation]
    e = [[a[2][0] * 100 - a[2][1] * 100 for a in ablation], [a[2][2] * 100 - a[2][0] * 100 for a in ablation]]
    ax.barh(g, d, xerr=e, capsize=4, color="#2d6a4f")
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("Drop in top-1 when term removed (points)")
    ax.set_title(f"Ablation, test split (n={len(items)}), 95% paired bootstrap CI")
    fig.tight_layout()
    fig.savefig(CHART_DIR / "ablation.png", dpi=150)
    plt.close(fig)


def write_unlabeled_sheet(items, recs):
    """Picks (from any system) that no human has seen, shuffled and unattributed, for a blind labeling pass."""
    import random
    seen, rows = set(), []
    for rs in recs.values():
        for it, r in zip(items, rs):
            if r["unlabeled_pick"] and (it["id"], r["pick"]["fdcId"]) not in seen:
                seen.add((it["id"], r["pick"]["fdcId"]))
                p = r["pick"]
                rows.append({"query_id": it["id"], "query": it["query"], "shown_pos": 0, "fdc_id": p["fdcId"],
                             "description": p.get("description", ""), "data_type": p.get("dataType", ""),
                             "kcal_per_100g": kcal_per_100g(p), "acceptable": ""})
    random.Random(SEED).shuffle(rows)
    write_csv(BENCH / "unlabeled_picks_sheet.csv", rows, SHEET_FIELDS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["tune", "report"])
    ap.add_argument("--max-calls", type=int, default=500)
    args = ap.parse_args()
    setup_cache(args.max_calls)
    {"tune": cmd_tune, "report": cmd_report}[args.command](args)


if __name__ == "__main__":
    main()
