"""Validate chance corrections against enumeration, and real controller draws."""
from itertools import combinations
from statistics import mean
from unittest.mock import patch

import pytest

from durak.controller import GameController
from durak.engine.dummy import DummyEngine
from durak.engine.matchup import DealRandom, play_game
from durak.engine.test_nextgen import game
from durak.luck import LuckTracker, WEIGHTS, advantage, expected_advantage, features
from durak.utils.cards import DurakCard


def cards(text):
    return list(map(DurakCard, text.split()))


def test_hand_features_distinguish_quality_fit_and_duplicates():
    ours = cards('8H TS TC TD AS 7C')
    enemy = cards('7H 6D 9S AH')
    assert features(ours, enemy, 'S') == {
        'trumps': 2, 'ranks': 23 / 8, 'answers': 2, 'pairs': 3, 'suits': 3}
    assert features(cards('AH'), cards('6H'), 'S')['answers'] == 0
    assert features(cards('6H'), cards('7H'), 'S')['suits'] == 0
    assert advantage(cards('AS'), cards('6D'), 'S')['trumps'] > 0
    assert advantage(cards('AH'), cards('6D'), 'S')['ranks'] > 0


@pytest.mark.parametrize('count', range(7))
@pytest.mark.parametrize('trump', ['S', 'H'])
def test_analytic_expectation_matches_every_possible_draw(count, trump):
    # Includes existing/new rank pairs, two possible cheap beaters, trump and
    # nontrump suit coverage, and new cards the opponent can cheaply beat.
    hand, enemy = cards('8C TS 7H'), cards('6H 9S QD KC')
    pool = cards('8H 8D 9H TC JD AS')
    expected = expected_advantage(hand, enemy, pool, count, trump)
    realized = [advantage(hand + list(draw), enemy, trump)
                for draw in combinations(pool, count)]
    for key in WEIGHTS:
        assert expected[key] == pytest.approx(mean(value[key] for value in realized), abs=1e-14)


@pytest.mark.parametrize('seat', [0, 1])
@pytest.mark.parametrize('count', [1, 2, 3, 4])
def test_refill_corrections_average_to_zero_and_exclude_face_up_trump(seat, count):
    first, second = cards('7H TC'), cards('8C 9H')
    pool, bottom = cards('8H 9C TS AH'), cards('AS')
    increments = []
    for draw in combinations(pool, count):
        stock = list(draw) + [c for c in pool if c not in draw] + bottom
        tracker = LuckTracker(first, second, 'AS')
        tracker.observe_refill(seat, first, second, stock, count)
        increments.append(tracker.report()['refills'])
    assert mean(increments) == pytest.approx(0, abs=1e-14)
    if count < len(pool):
        assert max(increments) > min(increments)


def test_seat_symmetry_order_invariance_and_deterministic_last_draw():
    first, second, stock = cards('7H TC 6S'), cards('8C 9H QD'), cards('8H TS AS')
    a, b = LuckTracker(first, second, 'AS'), LuckTracker(second, first, 'AS')
    assert a.report() == LuckTracker(first[::-1], second[::-1], 'AS').report()
    for tracker, seat, hands in ((a, 0, (first, second)), (b, 1, (second, first))):
        tracker.observe_refill(seat, *hands, stock, 1)
    for key in ('opening', 'refills', 'total'):
        assert a.report()[key] == pytest.approx(-b.report()[key])
    before = a.report()['refills']
    a.observe_refill(0, first, second, stock, 6)
    a.observe_refill(1, first, second, cards('AS'), 1)
    assert a.report()['refills'] == before


def test_taking_and_playing_do_not_count_as_luck_and_refills_use_post_pickup_hands():
    controller = game(cards('7C QD'), cards('AH KS'), table=cards('6C'), phase='giving_more')
    controller._deck = cards('8H 9H TS JD 7D AS')
    tracker = controller._luck = LuckTracker(controller._player1.cards, controller._player2.cards, 'AS')
    opening = tracker.report()
    controller.register_give_more([])
    assert tracker.report() == opening
    # The taker now holds 6C and draws first. Only the actual three stock cards
    # are measured, not the picked-up 6C; the opponent's final batch (including
    # the public ace) is deterministic.
    expected = LuckTracker(controller._player1.cards, controller._player2.cards, 'AS')
    expected.observe_refill(1, cards('7C QD'), cards('AH KS 6C'), controller._deck, 3)
    controller.deal()
    assert tracker.report()['refills'] == pytest.approx(expected.report()['refills'])
    assert tracker.report()['cards_drawn'] == 6
    assert set(controller._player2.cards) == set(cards('AH KS 6C 8H 9H TS'))


def test_opening_expectation_is_zero_over_all_allocations():
    pool = cards('6C 7H 8H TS AS 8C')
    values = []
    for hand in combinations(pool, 3):
        enemy = [c for c in pool if c not in hand]
        values.append(LuckTracker(hand, enemy, '9S').report()['opening'])
    assert mean(values) == pytest.approx(0, abs=1e-14)


def test_tracking_is_reproducible_and_does_not_change_randomness_or_outcome():
    reports, winners = [], []
    for _ in range(2):
        details = {}
        winners.append(play_game(DummyEngine(), DummyEngine(), 7832, details=details))
        reports.append(details['luck'])
    assert reports[0] == reports[1]
    assert reports[0]['cards_drawn'] == 24
    with patch.object(LuckTracker, 'observe_refill'):
        assert play_game(DummyEngine(), DummyEngine(), 7832) == winners[0] == winners[1]
    rng = DealRandom(5)
    with patch('durak.controller.random', rng):
        controller = GameController()
        controller._logger_enabled = False
        controller.start_new_game()
        state = rng.getstate()
        assert controller.luck_report() is None
        assert 'luck' not in controller.get_game_data_for('player1')
        controller._luck.report()
        assert rng.getstate() == state
        old = controller._luck
        controller.start_new_game()
        assert controller._luck is not old
        assert controller._luck.report()['refills'] == 0
