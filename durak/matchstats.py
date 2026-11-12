"""Luck-adjusted scores with uncertainty over independent deals, not seats."""
from math import log10, sqrt
from statistics import mean, stdev

from durak.luck import MODEL


def _t95(df):
    # Two-sided 95% Student t critical values; expansion above 30 df.
    small = (12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306,
             2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131, 2.120,
             2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064,
             2.060, 2.056, 2.052, 2.048, 2.045, 2.042)
    if df <= len(small):
        return small[df - 1]
    z = 1.959963984540054
    return z + (z ** 3 + z) / (4 * df) + (5 * z ** 5 + 16 * z ** 3 + 3 * z) / (96 * df ** 2)


def _elo(score):
    return 400 * log10(score / (1 - score)) if 0 < score < 1 else None


def _estimate(values):
    score = mean(values)
    se = stdev(values) / sqrt(len(values)) if len(values) > 1 else None
    # No observed variation isn't evidence of certainty (e.g. two wins).
    interval = None
    if se:
        margin = _t95(len(values) - 1) * se
        interval = [score - margin, score + margin]
    return {'score': score, 'standard_error': se, 'ci95': interval,
            'elo_difference': _elo(score),
            'elo_ci95': [_elo(value) for value in interval] if interval else None}


def summarize_scores(blocks):
    """Each independent block contains equal-count games: (result, signed luck).

    Use two-game blocks for swapped-seat deals, singleton blocks for independent
    shuffles. Unclipped result-luck is an unbiased chance-control-variate score;
    clipping individual games would destroy that property. Coefficients must
    remain fixed independently of the outcomes being evaluated.
    """
    if not blocks or not blocks[0] or any(len(block) != len(blocks[0]) for block in blocks):
        raise ValueError('need nonempty, equally sized independent blocks')
    raw = [mean(result for result, luck in block) for block in blocks]
    adjusted = [mean(result - luck for result, luck in block) for block in blocks]
    ordinary, corrected = _estimate(raw), _estimate(adjusted)
    raw_se, adjusted_se = ordinary['standard_error'], corrected['standard_error']
    return {'luck_model': MODEL, 'independent_deals': len(blocks),
            'games_per_deal': len(blocks[0]), 'mean_luck': mean(raw) - mean(adjusted),
            'raw': ordinary, 'luck_adjusted': corrected,
            'variance_ratio': (adjusted_se / raw_se) ** 2 if raw_se and adjusted_se is not None else None,
            'interval_method': 'approximate 95% Student t over independent deal averages'}
