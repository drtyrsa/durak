"""Reproducible, paired-deal headless matches between built-in engines."""
import argparse
from collections import Counter
import json
from random import Random
from statistics import median
from time import perf_counter
from unittest.mock import patch

from durak.controller import GameController
from durak.engine.dummy import DummyEngine
from durak.engine.nextgen import NextGenEngine
from durak.engine.puppeteer import PuppeteerEngine
from durak.engine.smart_runner import SmartRunnerEngine
from durak.utils.cards import DurakCard


class DealRandom(Random):
    def shuffle(self, cards):
        # Controller starts from a set; normalize Python's randomized hash order.
        cards.sort()
        super().shuffle(cards)


def play_game(first, second, seed, timings=None):
    """Return winner seat (0/1), or None for a draw; validate every action."""
    controller = GameController()
    controller._logger_enabled = False
    with patch('durak.controller.random', DealRandom(seed)):
        deal = controller.start_new_game()
    engines = (first, second)
    players = (controller.PLAYER1, controller.PLAYER2)
    for index, engine in enumerate(engines):
        engine.init(deal['trump'])
        engine.deal(deal['player%d_cards' % (index + 1)],
                    controller.get_game_data_for(players[index]))
    phases = {'moving': 'move', 'responding': 'respond', 'giving_more': 'give_more'}
    for _ in range(5000):
        if controller.is_game_over():
            return players.index(controller.winner) if controller.winner else None
        if controller.state == controller.States.DEALING:
            dealt = controller.deal()
            for index, engine in enumerate(engines):
                engine.deal(dealt['player%d_cards' % (index + 1)],
                            controller.get_game_data_for(players[index]))
        else:
            phase = phases[controller.state]
            index = int(not controller.is_player1_to_move()) ^ (phase == 'respond')
            data = controller.get_game_data_for(players[index])
            start = perf_counter()
            output = getattr(engines[index], phase)(controller.on_table, data)
            if timings is not None and data['deck_count'] > 0:
                timings[index].append(perf_counter() - start)
            cards = tuple(map(DurakCard, str(output).split()))
            getattr(controller, 'register_' + ('response' if phase == 'respond' else phase))(
                cards if phase == 'give_more' else (cards[0] if cards else None))
        for index, player in enumerate((controller._player1, controller._player2)):
            if engines[index]._cards != player.cards:
                raise AssertionError('engine hand diverged from controller')
            memory = (engines[index]._memory.enemy if isinstance(engines[index], NextGenEngine)
                      else engines[index]._enemy if isinstance(
                          engines[index], (SmartRunnerEngine, PuppeteerEngine))
                      else None)
            if memory is not None and controller.state == 'moving':
                enemy = (controller._player2, controller._player1)[index]
                # Just-played cards are still in memory until the next observation.
                remembered = memory - set(controller.on_table)
                if not remembered <= enemy.cards:
                    raise AssertionError('engine remembered cards the opponent does not hold')
    raise RuntimeError('game exceeded 5000 actions (seed %d)' % seed)


ENGINES = {
    'nextgen': NextGenEngine,
    'previous': lambda: NextGenEngine(middlegame='dummy'),  # Dummy middlegame, same endgame
    'smart_runner': SmartRunnerEngine,
    'puppeteer': PuppeteerEngine,
    'dummy': DummyEngine,
}


def benchmark(pairs=100, seed=0, opponent='previous', engine='nextgen'):
    if pairs < 1:
        raise ValueError('pairs must be positive')
    if opponent not in ENGINES or engine not in ENGINES:
        raise ValueError('engines must be one of: ' + ', '.join(ENGINES))
    scores, timings = Counter(), []
    start = perf_counter()
    for deal_seed in range(seed, seed + pairs):
        for seat in range(2):
            engines = [ENGINES[engine](), ENGINES[opponent]()]
            if seat:
                engines.reverse()
            game_timings = ([], [])
            winner = play_game(*engines, deal_seed, game_timings)
            timings.extend(game_timings[seat])
            scores['draws' if winner is None else 'wins' if winner == seat else 'losses'] += 1
    games = pairs * 2
    return {'engine': engine, 'opponent': opponent, 'pairs': pairs, 'games': games, 'seed': seed,
            **{key: scores[key] for key in ('wins', 'losses', 'draws')},
            'score': (scores['wins'] + scores['draws'] / 2) / games,
            'seconds': perf_counter() - start,
            'median_middlegame_ms': median(timings) * 1000,
            'max_middlegame_ms': max(timings) * 1000}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs', type=int, default=100,
                        help='each deal is played twice, swapping engine seats')
    parser.add_argument('--seed', type=int, default=0, help='first deal seed')
    parser.add_argument('--engine', choices=sorted(ENGINES), default='nextgen',
                        help='engine whose score is reported (default: nextgen)')
    parser.add_argument('--opponent', choices=sorted(ENGINES), default='previous')
    args = parser.parse_args()
    try:
        result = benchmark(args.pairs, args.seed, args.opponent, args.engine)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
