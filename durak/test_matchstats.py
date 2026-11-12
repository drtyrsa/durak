import json
from math import sqrt
from unittest.mock import patch

import pytest

from durak.autoplay import _do_autoplay
from durak.engine.matchup import benchmark
from durak.matchstats import summarize_scores


def test_lucky_wins_count_less_unlucky_wins_more_and_losses_adjust_too():
    assert summarize_scores([[(1, 0.2)]])['luck_adjusted']['score'] == 0.8
    assert summarize_scores([[(1, -0.2)]])['luck_adjusted']['score'] == 1.2
    assert summarize_scores([[(0, -0.2)]])['luck_adjusted']['score'] == 0.2
    assert summarize_scores([[(0.5, 0.1)]])['luck_adjusted']['score'] == 0.4
    # Scores above one are intentional; clipping is biased.
    assert summarize_scores([[(1, -0.2)]])['luck_adjusted']['elo_difference'] is None


def test_uncertainty_clusters_games_sharing_a_deal():
    result = summarize_scores([[(1, 0.1), (1, 0.1)], [(0, -0.1), (0, -0.1)]])
    assert result['independent_deals'] == 2
    assert result['raw']['standard_error'] == pytest.approx(0.5)
    assert result['luck_adjusted']['standard_error'] == pytest.approx(0.4)
    assert result['variance_ratio'] == pytest.approx(0.64)
    assert result['raw']['ci95'] == pytest.approx([0.5 - 12.706 * 0.5, 0.5 + 12.706 * 0.5])
    assert result['luck_adjusted']['elo_difference'] == 0
    # Treating four games as independent would give a spurious smaller SE.
    singles = summarize_scores([[(1, 0)], [(1, 0)], [(0, 0)], [(0, 0)]])
    assert singles['raw']['standard_error'] == pytest.approx(1 / sqrt(12))


@pytest.mark.parametrize('scores', [[1], [0], [0.5], [1, 1], [0, 0], [0.5, 0.5]])
def test_small_or_constant_samples_do_not_claim_certainty(scores):
    result = summarize_scores([[(s, 0)] for s in scores])
    assert result['raw']['ci95'] is None
    assert result['luck_adjusted']['ci95'] is None
    json.dumps(result, allow_nan=False)


def test_elo_conversion_and_player_swap():
    blocks = [[(1, 0.1)], [(0.5, -0.1)], [(1, 0)], [(0.5, 0)]]
    ours = summarize_scores(blocks)
    theirs = summarize_scores([[(1 - r, -luck) for r, luck in block] for block in blocks])
    assert ours['raw']['elo_difference'] == pytest.approx(190.8485, abs=0.0001)
    assert theirs['luck_adjusted']['score'] == pytest.approx(1 - ours['luck_adjusted']['score'])
    assert theirs['luck_adjusted']['elo_difference'] == pytest.approx(-ours['luck_adjusted']['elo_difference'])


def test_paired_benchmark_orients_luck_for_the_selected_engine():
    def fake_game(first, second, seed, timings, details):
        timings[0].append(0.001)
        timings[1].append(0.001)
        details['luck'] = {'total': 0.25}
        return 0
    with patch('durak.engine.matchup.play_game', side_effect=fake_game):
        result = benchmark(pairs=3, engine='dummy', opponent='dummy')
    assert result['wins'] == result['losses'] == 3
    assert result['score'] == result['strength']['luck_adjusted']['score'] == 0.5
    assert result['strength']['mean_luck'] == 0
    assert result['strength']['games_per_deal'] == 2


def test_autoplay_reports_game_strength_with_independent_shuffles(capsys):
    def fake_game(first, second, filename, details):
        details['luck'] = {'total': 0.2}
        return 1
    with patch('durak.autoplay._play_game', side_effect=fake_game):
        _do_autoplay('one', 'two', 1, 2)
    output = capsys.readouterr().out
    result = json.loads(output[output.index('{'):])
    assert result['games_per_deal'] == 1
    assert result['raw']['score'] == 1
    assert result['luck_adjusted']['score'] == 0.8
