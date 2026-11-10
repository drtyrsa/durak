"""NextGen engine: exact endgames, with room for a stronger middlegame."""
import argparse

from durak.engine.dummy import DummyEngine
from durak.engine.endgame import EndgameSolver, SearchLimitReached
from durak.utils.cards import DurakCard


class NextGenEngine(DummyEngine):
    """Dummy middlegame plus exact endgame search when within its budget."""

    def __init__(self, max_cards=12, max_nodes=500_000):
        if max_cards < 2 or max_cards > 36:
            raise ValueError('max_cards must be between 2 and 36')
        if max_nodes is not None and max_nodes < 1:
            raise ValueError('max_nodes must be positive or None')
        self.max_cards = max_cards
        self.max_nodes = max_nodes
        self._solver = None
        self.last_solution = None
        self.fallback_reason = None

    def init(self, trump):
        self._trump = DurakCard(trump)
        self._solver = None
        self.last_solution = None
        self.fallback_reason = None
        return super().init(trump)

    def _choose(self, phase, on_table, gamedata):
        self.last_solution = None
        self.fallback_reason = None
        if gamedata.get('deck_count') != 0:
            self.fallback_reason = 'deck is not known to be empty'
            return None
        if 'discarded' not in gamedata or 'enemy_count' not in gamedata:
            self.fallback_reason = 'incomplete game data'
            return None

        table = set(map(DurakCard, on_table))
        discarded = set(map(DurakCard, gamedata['discarded']))
        enemy = DurakCard.all() - self._cards - table - discarded
        if (len(enemy) != gamedata['enemy_count'] or len(table) != len(on_table)
                or self._cards & table or self._cards & discarded or table & discarded):
            self.fallback_reason = 'inconsistent game data'
            return None
        active = self._cards | enemy | table
        if len(active) > self.max_cards:
            self.fallback_reason = 'card limit reached'
            return None
        if self._solver is None or not active.issubset(self._solver.bits):
            self._solver = EndgameSolver(active, self._trump, self.max_nodes)

        attacker, defender = ((enemy, self._cards) if phase == 'respond'
                              else (self._cards, enemy))
        try:
            solution = self._solver.solve(attacker, defender, on_table, phase)
        except SearchLimitReached:
            self.fallback_reason = 'search budget reached'
            return None
        self.last_solution = solution
        self._cards.difference_update(solution.cards)
        return ' '.join(map(str, solution.cards))

    def move(self, on_table, gamedata):
        result = self._choose('move', on_table, gamedata)
        return super().move(on_table, gamedata) if result is None else result

    def respond(self, on_table, gamedata):
        result = self._choose('respond', on_table, gamedata)
        return super().respond(on_table, gamedata) if result is None else result

    def give_more(self, on_table, gamedata):
        result = self._choose('give_more', on_table, gamedata)
        return super().give_more(on_table, gamedata) if result is None else result


def main():
    parser = argparse.ArgumentParser(description='NextGen Durak engine (stdin/stdout protocol)')
    parser.add_argument('--max-cards', type=int, default=12,
                        help='maximum live cards including the table (default: 12)')
    parser.add_argument('--max-nodes', type=int, default=500_000,
                        help='uncached positions per decision (default: 500000; 0: unlimited)')
    args = parser.parse_args()
    try:
        engine = NextGenEngine(args.max_cards, args.max_nodes or None)
    except ValueError as error:
        parser.error(str(error))
    engine.run()


if __name__ == '__main__':
    main()
