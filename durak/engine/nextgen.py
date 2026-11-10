"""NextGen engine: public-information strategy and exact endgame search."""
import argparse
from time import perf_counter

from durak.engine.dummy import DummyEngine
from durak.engine.endgame import EndgameSolver, SearchLimitReached
from durak.engine.middlegame import CardMemory, MiddlegamePolicy
from durak.utils.cards import DurakCard


class NextGenEngine(DummyEngine):
    """Strategic middlegame plus exact endgame search when within its budget."""

    def __init__(self, max_cards=12, max_nodes=500_000, middlegame='smart', explain_decisions=False):
        if max_cards < 2 or max_cards > 36:
            raise ValueError('max_cards must be between 2 and 36')
        if max_nodes is not None and max_nodes < 1:
            raise ValueError('max_nodes must be positive or None')
        if middlegame not in ('smart', 'dummy'):
            raise ValueError('middlegame must be smart or dummy')
        self.middlegame = middlegame
        self.max_cards = max_cards
        self.max_nodes = max_nodes
        self._solver = None
        self.last_solution = None
        self.fallback_reason = None
        self.explain_decisions = explain_decisions
        self.last_decision = None
        self._decision_number = 0

    def init(self, trump):
        self._trump = DurakCard(trump)
        self._solver = None
        self.last_solution = None
        self.fallback_reason = None
        self.last_decision = None
        self._memory = CardMemory()
        return super().init(trump)

    def deal(self, cards, gamedata):
        result = super().deal(cards, gamedata)
        self._memory.deal(self._cards, gamedata)
        return result

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

    def _play(self, phase, on_table, gamedata):
        started = perf_counter()
        self.last_decision = None
        hand = list(map(str, sorted(self._cards))) if self.explain_decisions else None
        table = tuple(map(DurakCard, on_table))
        discarded = set(map(DurakCard, gamedata.get('discarded', ())))
        self._memory.observe(phase, table, self._cards, discarded)
        result = self._choose(phase, on_table, gamedata)
        strategy, explanation = 'exact', {}
        if (result is None and self.middlegame == 'smart'
                and MiddlegamePolicy.available(self._cards, self._trump, table, gamedata)):
            policy = MiddlegamePolicy(self._cards, self._trump, table, gamedata,
                                      self._memory.enemy)
            cards = getattr(policy, phase)()
            strategy = 'smart'
            if self.explain_decisions:
                explanation = policy.explain(phase, cards)
            self._cards.difference_update(cards)
            result = ' '.join(map(str, cards))
        elif result is None:
            strategy = 'dummy'
            result = getattr(super(), phase)(on_table, gamedata)
        self._memory.played(map(DurakCard, str(result).split()))
        self._decision_number += 1
        if self.explain_decisions:
            chosen = str(result).split()
            action = ('throw' if phase == 'give_more' else 'play' if chosen
                      else 'take' if phase == 'respond' else 'stop')
            if strategy == 'exact':
                explanation = {'reason': 'Exact minimax result for the chosen action.',
                               'outcome': self.last_solution.outcome, 'nodes': self.last_solution.nodes,
                               'candidates': None,
                               'alternative_note': 'Search may stop at a proven win; alternatives are not all evaluated.'}
            elif strategy == 'dummy':
                explanation = {'reason': 'Dummy policy: lowest eligible card; defend whenever possible.',
                               'candidates': None}
            self.last_decision = dict(explanation, decision_number=self._decision_number,
                phase=phase, hand=hand, on_table=list(map(str, table)), gamedata=gamedata,
                known_enemy=list(map(str, sorted(self._memory.enemy))), trump=str(self._trump),
                strategy=strategy, exact_unavailable_reason=self.fallback_reason,
                settings={'max_cards': self.max_cards, 'max_nodes': self.max_nodes, 'middlegame': self.middlegame},
                chosen={'action': action, 'cards': chosen}, elapsed_ms=(perf_counter() - started) * 1000)
        return result

    def move(self, on_table, gamedata):
        return self._play('move', on_table, gamedata)

    def respond(self, on_table, gamedata):
        return self._play('respond', on_table, gamedata)

    def give_more(self, on_table, gamedata):
        return self._play('give_more', on_table, gamedata)


def main():
    parser = argparse.ArgumentParser(description='NextGen Durak engine (stdin/stdout protocol)')
    parser.add_argument('--max-cards', type=int, default=12,
                        help='maximum live cards including the table (default: 12)')
    parser.add_argument('--max-nodes', type=int, default=500_000,
                        help='uncached positions per decision (default: 500000; 0: unlimited)')
    parser.add_argument('--middlegame', choices=('smart', 'dummy'), default='smart',
                        help='strategy while cards remain in the deck (default: smart)')
    args = parser.parse_args()
    try:
        engine = NextGenEngine(args.max_cards, args.max_nodes or None, args.middlegame)
    except ValueError as error:
        parser.error(str(error))
    engine.run()


if __name__ == '__main__':
    main()
