"""Ranking metrics, bootstrap confidence intervals and Cohen's kappa. Pure functions, no I/O."""
import random


def first_rank(ranked_ids, acceptable):
    """1-based rank of the first acceptable id, or None if none appears."""
    for i, fid in enumerate(ranked_ids, start=1):
        if fid in acceptable:
            return i
    return None


def per_query_scores(rank):
    """(top1, top3, reciprocal rank) for one query."""
    if rank is None:
        return 0.0, 0.0, 0.0
    return float(rank == 1), float(rank <= 3), 1.0 / rank


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def bootstrap_ci(values, n_resamples=1000, seed=0, alpha=0.05):
    """Percentile bootstrap CI for the mean, resampling queries with replacement."""
    rng = random.Random(seed)
    n = len(values)
    if n == 0:
        return float("nan"), float("nan")
    means = sorted(mean([values[rng.randrange(n)] for _ in range(n)]) for _ in range(n_resamples))
    lo = means[int((alpha / 2) * n_resamples)]
    hi = means[min(n_resamples - 1, int((1 - alpha / 2) * n_resamples))]
    return lo, hi


def paired_bootstrap_diff(a, b, n_resamples=1000, seed=0, alpha=0.05):
    """Mean(a - b) with a percentile CI; a and b are per-query values over the same queries."""
    assert len(a) == len(b)
    d = [x - y for x, y in zip(a, b)]
    lo, hi = bootstrap_ci(d, n_resamples, seed, alpha)
    return mean(d), lo, hi


def cohen_kappa(labels_a, labels_b):
    """Cohen's kappa for two raters' parallel categorical labels. Returns (kappa, observed_agreement)."""
    assert len(labels_a) == len(labels_b) and labels_a
    n = len(labels_a)
    po = sum(x == y for x, y in zip(labels_a, labels_b)) / n
    cats = set(labels_a) | set(labels_b)
    pe = sum((labels_a.count(c) / n) * (labels_b.count(c) / n) for c in cats)
    kappa = 1.0 if pe == 1 else (po - pe) / (1 - pe)
    return kappa, po


def mape(estimates, references):
    """Mean absolute percentage error over pairs with a positive reference. Returns (mape %, n_used)."""
    errs = [abs(e - r) / r * 100 for e, r in zip(estimates, references) if r and r > 0]
    return (mean(errs) if errs else float("nan")), len(errs)
