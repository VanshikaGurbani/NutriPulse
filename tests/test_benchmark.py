"""Tests the benchmark machinery on SYNTHETIC data. Nothing here is a reported result."""
import json

import pytest

from benchmark import metrics, run_benchmark as rb
from tests.conftest import food


def test_first_rank_and_scores():
    assert metrics.first_rank([5, 6, 7], {7}) == 3
    assert metrics.first_rank([5], {9}) is None
    assert metrics.per_query_scores(1) == (1.0, 1.0, 1.0)
    assert metrics.per_query_scores(3) == (0.0, 1.0, pytest.approx(1 / 3))
    assert metrics.per_query_scores(None) == (0.0, 0.0, 0.0)


def test_bootstrap_ci_brackets_mean_and_is_seeded():
    vals = [1.0] * 30 + [0.0] * 70
    lo, hi = metrics.bootstrap_ci(vals, 1000, seed=1)
    assert lo < 0.3 < hi and 0.15 < lo and hi < 0.45
    assert metrics.bootstrap_ci(vals, 1000, seed=1) == (lo, hi)
    assert metrics.bootstrap_ci([1.0] * 50, 1000)[0] == 1.0


def test_paired_diff_detects_real_gap():
    a = [1.0] * 80 + [0.0] * 20
    b = [1.0] * 40 + [0.0] * 60
    d, lo, hi = metrics.paired_bootstrap_diff(a, b)
    assert d == pytest.approx(0.4) and lo > 0
    d0, lo0, hi0 = metrics.paired_bootstrap_diff(a, a)
    assert d0 == 0 and lo0 <= 0 <= hi0


def test_cohen_kappa_known_values():
    k, po = metrics.cohen_kappa(list("yyyynnnn"), list("yyyynnnn"))
    assert k == 1.0 and po == 1.0
    k, po = metrics.cohen_kappa(list("yynn"), list("ynyn"))       # po=.5, pe=.5 -> kappa 0
    assert k == pytest.approx(0.0) and po == 0.5
    # textbook 2x2: a=20,b=5,c=10,d=15 -> po=.7, pe=.5 -> kappa=.4
    la = ["y"] * 25 + ["n"] * 25
    lb = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert metrics.cohen_kappa(la, lb)[0] == pytest.approx(0.4)


def test_mape():
    assert metrics.mape([110, 90], [100, 100]) == (pytest.approx(10.0), 2)
    assert metrics.mape([5], [0])[1] == 0


def synthetic_items(n=30):
    """Pool where the right answer is last in API order but the scorer can find it."""
    items = []
    for i in range(n):
        q = f"thing{i}"
        pool = [food(f"Bread, {q}", 280, fdc_id=1000 + i), food(f"{q.title()}, cooked", 70, fdc_id=2000 + i)]
        items.append({"id": f"q{i}", "query": q, "acceptable": {2000 + i}, "pool": pool,
                      "shown": {f["fdcId"] for f in pool}, "category": ""})
    return items


def test_evaluate_and_summarize_on_synthetic_pools():
    items = synthetic_items()
    naive = rb.summarize(rb.evaluate(items, rb.rank_naive))
    scorer = rb.summarize(rb.evaluate(items, lambda it: rb.rank_scorer(it)))
    assert naive["top1"][0] == 0.0 and scorer["top1"][0] == 1.0


def test_tuning_never_worsens_dev_objective():
    items = synthetic_items(25)
    w, before, after = rb.tune_weights(items)
    assert after[0] >= before[0]


def test_explain_miss_names_a_term():
    items = synthetic_items(1)
    items[0]["acceptable"] = {1000}                       # force a "miss": acceptable is the lower-scored item
    rec = rb.evaluate(items, rb.rank_scorer)[0]
    ex = rb.explain_miss(items[0], rec, rec)
    assert rec["rank"] == 2 and "driven by" in ex["cause"] and ex["gap"] > 0


def test_kcal_agreement_tolerance():
    assert rb.kcal_agrees(100, [110]) and not rb.kcal_agrees(100, [150])
    assert rb.kcal_agrees(2, [6])                         # absolute floor of 5 kcal


def test_report_end_to_end_on_synthetic_data(tmp_path, monkeypatch, capsys):
    from benchmark import common
    qpath = tmp_path / "queries.csv"
    rows = [{"id": f"q{i}", "query": f"thing{i}", "split": "dev" if i < 25 else "test",
             "acceptable_fdc_ids": str(2000 + i), "notes": "category=x;labeled=1"} for i in range(50)]
    common.write_csv(qpath, rows, ["id", "query", "split", "acceptable_fdc_ids", "notes"])
    pools = {f"thing{i}": [[food(f"Bread, thing{i}", 280, fdc_id=1000 + i)],
                           [food(f"Thing{i}, cooked", 70, fdc_id=2000 + i)], []] for i in range(50)}
    monkeypatch.setattr(common, "QUERIES_CSV", qpath)
    monkeypatch.setattr(rb, "QUERIES_CSV", qpath)
    monkeypatch.setattr(common, "load_queries", lambda split=None: [r for r in common.read_csv(qpath) if not split or r["split"] == split])
    monkeypatch.setattr(rb, "load_queries", common.load_queries)
    monkeypatch.setattr(rb.matching, "candidate_lists", lambda q: pools[q])
    monkeypatch.setattr(rb, "BENCH", tmp_path)
    monkeypatch.setattr(rb, "CHART_DIR", tmp_path / "charts")
    monkeypatch.setattr(rb, "TUNED_PATH", tmp_path / "tuned_weights.json")
    monkeypatch.setattr(rb.apis, "search_food_nlp", lambda q: None)

    rb.cmd_tune(None)
    tuned = json.loads((tmp_path / "tuned_weights.json").read_text(encoding="utf-8"))
    assert tuned["tuned_on"] == "dev" and tuned["n_dev"] == 25
    rb.cmd_report(None)
    md = (tmp_path / "results.md").read_text(encoding="utf-8")
    assert "Test split only" in md and "n = 25" in md and "Ablation" in md
    assert (tmp_path / "charts" / "accuracy_by_system.png").exists()


def test_report_refuses_partial_labels(monkeypatch, tmp_path):
    from benchmark import common
    qpath = tmp_path / "q.csv"
    common.write_csv(qpath, [{"id": "q1", "query": "rice", "split": "test", "acceptable_fdc_ids": "", "notes": "category=x"}],
                     ["id", "query", "split", "acceptable_fdc_ids", "notes"])
    monkeypatch.setattr(common, "load_queries", lambda split=None: common.read_csv(qpath))
    monkeypatch.setattr(rb, "load_queries", common.load_queries)
    with pytest.raises(SystemExit, match="not labelled"):
        rb.load_items("test")
