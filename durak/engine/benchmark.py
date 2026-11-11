"""Reproducible headless measurements of NextGen's exact endgame solver."""
import argparse
import json
from random import Random
from statistics import median
from time import perf_counter

from durak.engine.endgame import EndgameSolver, SearchLimitReached
from durak.utils.cards import DurakCard


def benchmark(samples=200, hand_size=6, seed=20261110, max_nodes=500_000, swindle_depth=3):
    if samples < 1 or not 1 <= hand_size <= 18:
        raise ValueError('samples must be positive and hand_size must be 1..18')
    random = Random(seed)
    deck = sorted(DurakCard.all())
    times, nodes = [], []
    limits = 0
    for _ in range(samples):
        cards = random.sample(deck, 2 * hand_size)
        solver = EndgameSolver(cards, '6S', max_nodes=max_nodes, swindle_depth=swindle_depth)
        start = perf_counter()
        try:
            solver.solve(cards[:hand_size], cards[hand_size:])
        except SearchLimitReached:
            limits += 1
        times.append(perf_counter() - start)
        nodes.append(solver.nodes)
    return {'samples': samples, 'cards_per_hand': hand_size, 'seed': seed,
            'max_nodes': max_nodes, 'swindle_depth': swindle_depth, 'solved': samples - limits, 'budget_exhausted': limits,
            'median_seconds': median(times), 'max_seconds': max(times),
            'median_nodes': median(nodes), 'max_nodes_visited': max(nodes)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=200)
    parser.add_argument('--hand-size', type=int, default=6)
    parser.add_argument('--seed', type=int, default=20261110)
    parser.add_argument('--max-nodes', type=int, default=500_000,
                        help='per-position budget; 0 means unlimited')
    parser.add_argument('--swindle-depth', type=int, default=3,
                        help='tie-break depth in lost/drawn positions; 0 disables it')
    args = parser.parse_args()
    try:
        result = benchmark(args.samples, args.hand_size, args.seed, args.max_nodes or None,
                           args.swindle_depth)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
