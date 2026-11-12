"""Puppeteer: an engine that plays the opponent, not just the cards.

Every other engine here meets a fixed rival: perfect play in the endgame,
uniform hidden cards in Monte Carlo sampling, a hard-coded cheap policy
inside simulations. Puppeteer instead learns how this particular opponent
behaves while the game is being played:

- which attacks they defend and which they take, per attack bucket
  (low/mid/high plain cards and trumps);
- how willingly they spend a trump when nothing cheaper can beat;
- how often they lead trumps at a free lead, keep attacking in a bout,
  and how much of the throw-in limit they use when the defender takes.

Hidden cards make behaviour ambiguous: taking an attack only counts as
refusal if a beating card may be hidden in the opponent's hand. Every
observation is therefore weighted by the probability that the habit could
even show up, computed hypergeometrically over the cards the opponent may
hold. The estimates are prior-weighted counts, so early play assumes a
sane opponent until evidence arrives.

At each decision Puppeteer samples worlds consistent with the public
information and, in every world, plays out every legal candidate against a
stand-in driven by the learned profile, then finishes the line with the
shared fast rollout. The opponent's reply to an attack is evaluated
exactly: the beat and take branches are both rolled out and mixed with the
measured defence probability, so the profile sharpens estimates instead of
adding noise. Exploits are emergent, not hand-coded: against an opponent
who always beats cheap attacks, the search discovers junk attacks that
pull their trumps on its own. Close scores prefer keeping useful cards.
An empty deck switches to the exact EndgameSolver.
"""
import argparse
from math import comb, sqrt
from random import Random
from time import perf_counter
from zlib import crc32

from durak.engine.dummy import DummyEngine
from durak.engine.endgame import EndgameSolver, SearchLimitReached
from durak.engine.simulator import DRAW, GIVE, MOVE, RESPOND, STOPPED, Universe, rollout
from durak.utils.cards import DurakCard

ALL_CARDS = frozenset(DurakCard.all())

BUCKETS = ('low plain', 'mid plain', 'high plain', 'trump')
# Prior (agrees, declines) samples per attack bucket for "defend if a plain
# beater exists", plus single priors for the remaining habits.
DEFENCE_PRIOR = {0: (6.0, 1.0), 1: (4.0, 1.0), 2: (2.0, 1.5), 3: (1.5, 1.5)}
TRUMP_PRIOR = (1.5, 1.5)      # defend with a trump when only a trump can beat
LEAD_PRIOR = (1.0, 12.0)      # (lead a trump, lead a plain) at a free lead
CONTINUE_PRIOR = (5.0, 3.0)   # (attack again, stop) while eligible cards exist
THROWIN_PRIOR_SUM, THROWIN_PRIOR_N = 2.1, 3.0  # mean 0.7 of defender capacity


class OpponentProfile:
    """Online habit estimates for one opponent, from public observations only."""

    def __init__(self):
        self.beats = {b: 0.0 for b in range(4)}        # defended a plain-capable attack
        self.declines = {b: 0.0 for b in range(4)}    # took despite a possible plain beater
        self.trump_beats = 0.0                          # defended with a trump
        self.trump_declines = 0.0                       # took when only a trump may have beaten
        self.trump_leads = 0.0                          # free leads of a trump (plain weighed)
        self.plain_leads = 0.0                          # free leads of a plain (trump weighed)
        self.continues = 0.0                            # attacks added to a started bout
        self.stops = 0.0                                # passes, eligibility-weighed
        self.throwin_shares = []                        # throws / (defender hand size - 1)
        self.defences = 0
        self.takes = 0
        self.version = 0.0

    def record_defence(self, bucket, used_trump, plain_chance):
        """They defended an attack of this bucket, spending ``used_trump``.

        A trump defence is only evidence of plain-case willingness to the
        extent that a plain beater may have existed.
        """
        self.defences += 1
        self.beats[bucket] += plain_chance if used_trump else 1.0
        if used_trump:
            self.trump_beats += 1.0
        self.version += 1.0

    def record_take(self, bucket, plain_chance, any_chance):
        """They took an attack they may or may not have been able to beat."""
        self.takes += 1
        self.declines[bucket] += plain_chance
        self.trump_declines += max(0.0, any_chance - plain_chance)
        self.version += plain_chance + max(0.0, any_chance - plain_chance)

    def record_lead(self, led_trump, alternative_chance):
        if led_trump:
            self.trump_leads += alternative_chance
        else:
            self.plain_leads += alternative_chance
        self.version += alternative_chance

    def record_continuation(self):
        self.continues += 1.0
        self.version += 1.0

    def record_stop(self, eligible_chance):
        self.stops += eligible_chance
        self.version += eligible_chance

    def record_throwins(self, share):
        self.throwin_shares.append(share)
        self.version += 1.0

    def defence_rate(self, bucket):
        a, b = DEFENCE_PRIOR[bucket]
        agree, decline = a + self.beats[bucket], b + self.declines[bucket]
        return agree / (agree + decline)

    def trump_rate(self):
        agree, decline = (TRUMP_PRIOR[0] + self.trump_beats,
                           TRUMP_PRIOR[1] + self.trump_declines)
        return agree / (agree + decline)

    def lead_trump_rate(self):
        agree, decline = LEAD_PRIOR[0] + self.trump_leads, LEAD_PRIOR[1] + self.plain_leads
        return agree / (agree + decline)

    def continue_rate(self):
        agree, decline = (CONTINUE_PRIOR[0] + self.continues,
                          CONTINUE_PRIOR[1] + self.stops)
        return agree / (agree + decline)

    def throwin_share(self):
        total = THROWIN_PRIOR_SUM + sum(self.throwin_shares)
        return total / (THROWIN_PRIOR_N + len(self.throwin_shares))

    def report(self):
        return {'defence_rate': {name: round(self.defence_rate(b), 3)
                                  for b, name in enumerate(BUCKETS)},
                'trump_defence_rate': round(self.trump_rate(), 3),
                'lead_trump_rate': round(self.lead_trump_rate(), 3),
                'continue_rate': round(self.continue_rate(), 3),
                'throwin_share': round(self.throwin_share(), 3),
                'observations': {'defences': self.defences, 'takes': self.takes,
                                 'leads': round(self.trump_leads + self.plain_leads, 1),
                                 'continues': int(self.continues),
                                 'stops': round(self.stops, 1),
                                 'throwins': len(self.throwin_shares)}}


class PuppeteerEngine(DummyEngine):
    """Profiles the real opponent and exploits the profile inside simulations.

    Resource settings:

    - ``worlds``/``probe``: sampled worlds per decision; after ``probe``
      shared worlds, a candidate is dropped once it clearly trails the leader.
    - ``horizon``: opponent decisions driven by the profile in each rollout
      before both seats revert to the cheap policy.
    - ``leaf_deck``: with at most this many cards in the deck, rollouts stop
      when the sampled deck runs out and the exact solver scores the world
      (``leaf_worlds`` worlds, ``leaf_nodes`` per leaf, ``leaf_budget``
      per decision). 0 disables exact leaves.
    - ``max_cards``/``max_nodes``: exact search budget when the deck is empty.
    """

    def __init__(self, worlds=1024, probe=96, horizon=2, max_cards=36, max_nodes=500_000,
                 swindle_depth=3, leaf_deck=4, leaf_worlds=128, leaf_nodes=5_000,
                 leaf_budget=150_000, seed=0, explain_decisions=False):
        if worlds < 1 or probe < 1 or leaf_worlds < 1 or leaf_nodes < 1:
            raise ValueError('worlds, probe, leaf_worlds and leaf_nodes must be positive')
        if horizon < 0:
            raise ValueError('horizon must be non-negative')
        if not 2 <= max_cards <= 36:
            raise ValueError('max_cards must be between 2 and 36')
        if max_nodes is not None and max_nodes < 1:
            raise ValueError('max_nodes must be positive or None')
        if swindle_depth < 0 or leaf_deck < 0 or leaf_budget < 0:
            raise ValueError('swindle_depth, leaf_deck and leaf_budget must be non-negative')
        self.worlds = worlds
        self.probe = probe
        self.horizon = horizon
        self.max_cards = max_cards
        self.max_nodes = max_nodes
        self.swindle_depth = swindle_depth
        self.leaf_deck = leaf_deck
        self.leaf_worlds = leaf_worlds
        self.leaf_nodes = leaf_nodes
        self.leaf_budget = leaf_budget
        self.seed = seed
        self.explain_decisions = explain_decisions
        self.last_decision = None

    # Protocol ---------------------------------------------------------------

    def init(self, trump):
        result = super().init(trump)
        self._trump_card = DurakCard(trump)
        self._universe = Universe(self._trump_card)
        self._enemy = set()   # cards known to be in the opponent's hand
        self._seen = set()    # last observed table plus our later plays
        self._profile = OpponentProfile()
        self._solver = None
        self._ledger = []     # table cards as last known, ours included
        self._take = None     # snapshot of our take, for throw-in counting
        self._context = None  # belief snapshot for bout-end events
        self._last_defended = False
        self.last_decision = None
        return result

    def deal(self, cards, gamedata):
        self._settle_bout(gamedata)
        result = super().deal(cards, gamedata)
        self._enemy.difference_update(self._cards)
        self._remember((), gamedata)
        return result

    def move(self, on_table, gamedata):
        return self._decide('move', on_table, gamedata)

    def respond(self, on_table, gamedata):
        return self._decide('respond', on_table, gamedata)

    def give_more(self, on_table, gamedata):
        return self._decide('give_more', on_table, gamedata)

    # Knowledge ----------------------------------------------------------------

    def _remember(self, table, gamedata):
        """Track cards the opponent visibly picked up.

        A card we saw on the table that is now neither on it, discarded, nor
        in our hand was picked up by the opponent; this includes our throw-ins.
        Cards the opponent plays become public again.
        """
        if 'discarded' not in gamedata:
            return
        public = set(table) | set(map(DurakCard, gamedata['discarded']))
        self._enemy |= self._seen - public - self._cards
        self._enemy -= public | self._cards
        enemy_count = gamedata.get('enemy_count')
        if enemy_count is not None and len(self._enemy) > enemy_count:
            self._enemy = set()  # inconsistent: forget, don't guess
        self._seen = set(table)

    def _hidden(self, table, gamedata):
        """(unknown cards, free opponent slots, deck size), or None if unclear."""
        try:
            deck_count, enemy_count = gamedata['deck_count'], gamedata['enemy_count']
            discarded = set(map(DurakCard, gamedata['discarded']))
        except (KeyError, TypeError, ValueError):
            return None
        if not isinstance(deck_count, int) or not isinstance(enemy_count, int):
            return None
        unknown = ALL_CARDS - self._cards - set(table) - discarded - self._enemy
        slots = enemy_count - len(self._enemy)
        if slots < 0 or len(unknown) != slots + deck_count:
            return None
        if deck_count and self._trump_card not in unknown:
            return None  # the face-up trump is always the last card of the deck
        return unknown, slots, deck_count

    def bucket(self, card):
        if card.suit == self._trump_card.suit:
            return 3
        return min(card.numeric_rank // 3, 2)

    def _pool(self, hidden):
        """Unknown cards that can enter the opponent's hand before the deck ends.

        The face-up bottom trump is the deck's last card: while the deck is
        not empty it can never be in the opponent's hand, so it is excluded
        from the weight computations as well as from the sampled worlds.
        """
        unknown, slots, deck_count = hidden
        return unknown - {self._trump_card} if deck_count else unknown

    @staticmethod
    def _present(pool, slots, known, cards):
        """P(opponent holds a card from ``cards``), given public beliefs."""
        if cards & known:
            return 1.0
        return PuppeteerEngine._hyper(pool, slots, cards & pool)

    @staticmethod
    def _hyper(pool, slots, cards):
        if not cards or slots <= 0:
            return 0.0
        if slots >= len(pool):
            return 1.0
        return 1.0 - comb(len(pool) - len(cards), slots) / comb(len(pool), slots)

    def _beating(self, attack, possible):
        """Cards from ``possible`` that beat ``attack``."""
        trump_suit = self._trump_card.suit
        return {c for c in possible
                if (c.suit == attack.suit and c.numeric_rank > attack.numeric_rank)
                or (c.suit == trump_suit != attack.suit)}

    # Profiling ----------------------------------------------------------------

    def _watch(self, phase, table, hidden):
        """Profile the opponent's newly visible plays."""
        new = table[len(self._ledger):]
        if hidden is None or not new:
            return
        pool, slots = self._pool(hidden), hidden[1]
        trump_suit = self._trump_card.suit
        for offset, card in enumerate(new):
            index = len(self._ledger) + offset
            if phase == 'respond':
                if index == 0:
                    plain = {c for c in pool | self._enemy if c.suit != trump_suit}
                    chance = self._present(pool, slots, self._enemy, plain)
                    if card.suit == trump_suit:
                        self._profile.record_lead(True, chance)
                    else:
                        trumps = {c for c in pool | self._enemy if c.suit == trump_suit}
                        self._profile.record_lead(False, self._present(
                            pool, slots, self._enemy, trumps))
                else:
                    self._profile.record_continuation()
            elif index % 2:
                attack = table[index - 1]
                beaters = self._beating(attack, pool | self._enemy)
                plains = {c for c in beaters if c.suit != trump_suit}
                if card.suit == trump_suit:
                    plain_chance = self._present(pool, slots, self._enemy, plains)
                    self._profile.record_defence(self.bucket(attack), True, plain_chance)
                else:
                    self._profile.record_defence(self.bucket(attack), False, 1.0)

    def _record_take(self, table, hidden):
        """They took our last attack instead of beating it."""
        attack = table[-1]
        pool, slots = self._pool(hidden), hidden[1]
        beaters = self._beating(attack, pool | self._enemy)
        plains = {c for c in beaters if c.suit != self._trump_card.suit}
        plain_chance = self._present(pool, slots, self._enemy, plains)
        any_chance = self._present(pool, slots, self._enemy, beaters)
        self._profile.record_take(self.bucket(attack), plain_chance, any_chance)

    def _settle_bout(self, gamedata):
        """Profile events that are only visible when the bout resolves."""
        take, context = self._take, self._context
        if take is not None and 'enemy_count' in gamedata:
            self._count_throwins(take, gamedata)
        elif self._last_defended and context is not None:
            # They held the initiative after our defence and chose not to attack.
            ranks = {c.rank for c in context['table']}
            eligible = {c for c in context['possible'] if c.rank in ranks}
            self._profile.record_stop(self._present(
                context['pool'], context['slots'], context['known'], eligible))
        self._take = None
        self._last_defended = False
        self._ledger = []
        self._context = None

    def _count_throwins(self, take, gamedata):
        """Count the cards the opponent threw onto our take, if it is knowable.

        Refills mix with the table in the cards we receive, so the thrown
        count is found by trying every legal count and replaying the
        controller's exact refill accounting. Ambiguous counts are skipped.
        """
        cap = min(take['mine'] - 1, take['enemy'])
        if cap <= 0:
            return
        candidates = []
        for thrown in range(cap + 1):
            my_draw = min(max(0, 6 - take['mine'] - take['k'] - thrown), take['deck'])
            their_draw = min(max(0, 6 - take['enemy'] + thrown), take['deck'] - my_draw)
            enemy_now = take['enemy'] - thrown + their_draw
            deck_now = take['deck'] - my_draw - their_draw
            if (enemy_now == gamedata['enemy_count']
                    and deck_now == gamedata.get('deck_count', deck_now)):
                candidates.append(thrown)
        if len(candidates) != 1:
            return
        thrown = candidates[0]
        ranks = {c.rank for c in take['table']}
        eligible = {c for c in take['pool'] | take['known'] if c.rank in ranks}
        if thrown:
            self._profile.record_throwins(min(1.0, thrown / max(1, take['mine'] - 1)))
        elif self._present(take['pool'], take['slots'], take['known'],
                           eligible) >= 0.5:
            self._profile.record_throwins(0.0)

    def _snapshot(self, table, hidden):
        if hidden is None:
            return None
        pool = self._pool(hidden)
        return {'pool': pool, 'slots': hidden[1], 'known': frozenset(self._enemy),
                'table': tuple(table), 'possible': pool | self._enemy}

    def _take_snapshot(self, table, hidden, gamedata):
        return {'deck': gamedata['deck_count'], 'mine': len(self._cards),
                'enemy': gamedata['enemy_count'], 'k': len(table),
                'pool': self._pool(hidden), 'slots': hidden[1],
                'known': frozenset(self._enemy), 'table': tuple(table)}

    # Decisions ------------------------------------------------------------------

    def _decide(self, phase, on_table, gamedata):
        started = perf_counter()
        table = list(map(DurakCard, on_table))
        hand_before = sorted(self._cards)
        self._remember(table, gamedata)
        hidden = self._hidden(table, gamedata)
        self._watch(phase, table, hidden)
        if phase == 'give_more' and hidden is not None:
            self._record_take(table, hidden)
        info = {}
        cards = None
        if hidden is not None and hidden[2] == 0:
            cards = self._exact(phase, table, hidden, info)
        if cards is None and hidden is not None:
            cards = self._search(phase, table, gamedata, hidden, info)
        if cards is None:
            info['strategy'] = 'dummy'
            output = str(getattr(super(), phase)(on_table, gamedata))
            cards = list(map(DurakCard, output.split()))
        else:
            self._cards.difference_update(cards)
        self._ledger = table if phase == 'give_more' else table + list(cards)
        # A stop after our defence concerns every exposed rank, including
        # the rank of the card we just played.
        self._context = self._snapshot(self._ledger, hidden)
        self._seen.update(cards)
        if phase == 'respond':
            # The controller ends the bout automatically if either hand is
            # empty. Only a genuine continuation opportunity can teach restraint.
            self._last_defended = bool(cards and self._cards and gamedata.get('enemy_count', 0))
            if not cards and hidden is not None:
                self._take = self._take_snapshot(table, hidden, gamedata)
        if self.explain_decisions:
            self.last_decision = dict(
                info, phase=phase, hand=list(map(str, hand_before)),
                on_table=list(map(str, table)), gamedata=gamedata,
                known_enemy=list(map(str, sorted(self._enemy))),
                chosen=list(map(str, cards)), profile=self._profile.report(),
                settings={'worlds': self.worlds, 'probe': self.probe,
                          'horizon': self.horizon, 'max_cards': self.max_cards,
                          'max_nodes': self.max_nodes, 'swindle_depth': self.swindle_depth,
                          'leaf_deck': self.leaf_deck, 'leaf_worlds': self.leaf_worlds,
                          'leaf_nodes': self.leaf_nodes, 'leaf_budget': self.leaf_budget,
                          'seed': self.seed},
                elapsed_ms=(perf_counter() - started) * 1000)
        return ' '.join(map(str, cards))

    def _exact(self, phase, table, hidden, info):
        unknown, slots, _ = hidden
        enemy = unknown | self._enemy
        active = self._cards | enemy | set(table)
        if len(active) > self.max_cards:
            info['exact_search'] = {'status': 'card_limit', 'live_cards': len(active)}
            return None
        if self._solver is None or not active.issubset(self._solver.bits):
            self._solver = EndgameSolver(active, self._trump_card, self.max_nodes,
                                         self.swindle_depth)
        attacker, defender = (enemy, self._cards) if phase == 'respond' else (self._cards, enemy)
        try:
            solution = self._solver.solve(attacker, defender, table, phase)
        except SearchLimitReached:
            info['exact_search'] = {'status': 'node_limit', 'live_cards': len(active),
                                    'nodes': self._solver.nodes}
            return None
        info['exact_search'] = {'status': 'solved', 'live_cards': len(active)}
        info.update(strategy='exact', outcome=solution.outcome, nodes=solution.nodes,
                    expected_vs_random=solution.expected_vs_random)
        return list(solution.cards)

    def _candidates(self, phase, mine, table, pending, enemy_count):
        """Legal actions as masks, cheapest first; 0 = stop/take/throw nothing."""
        u = self._universe
        if phase == 'respond':
            return self._bits(mine & u.beaters[pending.bit_length() - 1]) + [0]
        if phase == 'move':
            if not table:
                return self._bits(mine)
            return self._bits(mine & u.ranks(table)) + [0]
        eligible = self._bits(mine & u.ranks(table))
        eligible.sort(key=lambda bit: (self._thrust('give_more', bit, mine, table), bit))
        prefixes, given = [0], 0
        for bit in eligible[:max(0, enemy_count - 1)]:
            given |= bit
            prefixes.append(given)
        return prefixes

    @staticmethod
    def _bits(mask):
        bits = []
        while mask:
            low = mask & -mask
            mask ^= low
            bits.append(low)
        return bits

    def _thrust(self, phase, candidate, mine, table):
        """Preference for keeping useful cards when scores are indistinguishable."""
        u = self._universe
        if not candidate:
            if phase != 'respond':
                return 0.0
            useful = sum(0.2 for bit in self._bits(table)
                         if bit & u.trumps or u.rank[bit.bit_length() - 1] >= 6)
            bloat = max(0, (mine | table).bit_count() - 6)
            return 0.8 + 0.4 * (table.bit_count() - 1) + 0.12 * bloat - useful
        cost = 0.0
        for bit in self._bits(candidate):
            rank = u.rank[bit.bit_length() - 1] / 8
            if bit & u.trumps:
                cost += 1.4 + rank
            else:
                cost += rank - (0.1 if phase == 'give_more' else 0.0)
        return cost

    def _search(self, phase, table, gamedata, hidden, info):
        u = self._universe
        unknown, slots, deck_count = hidden
        mine = u.mask(self._cards)
        table_mask = u.mask(table)
        pending = u.bit[table[-1]] if phase == 'respond' else 0
        candidates = self._candidates(phase, mine, table_mask, pending, gamedata['enemy_count'])
        if len(candidates) == 1:
            info['strategy'] = 'forced'
            return u.unpack(candidates[0])
        known = u.mask(self._enemy)
        bottom = u.bit[self._trump_card] if deck_count else 0
        pool = sorted(u.bit[card] for card in unknown if u.bit[card] != bottom)
        key = '|'.join(map(str, (self.seed, phase, sorted(self._cards), table,
                                 sorted(unknown), sorted(self._enemy), self._profile.version)))
        rng = Random(crc32(key.encode()))
        attacker = 1 if phase == 'respond' else 0
        mode = {'move': MOVE, 'respond': RESPOND, 'give_more': GIVE}[phase]
        worlds = self.worlds if deck_count else 1  # an empty deck hides nothing
        exact_leaves = 0 < deck_count <= self.leaf_deck
        if exact_leaves:
            worlds = min(worlds, self.leaf_worlds)
        probe = min(self.probe, worlds)
        results = [[] for _ in candidates]
        costs = [self._thrust(phase, c, mine, table_mask) for c in candidates]
        active = list(range(len(candidates)))
        done, budget = 0, self.leaf_budget
        while done < worlds and len(active) > 1:
            target = probe if done < probe else worlds
            for _ in range(target - done):
                done += 1
                rng.shuffle(pool)
                enemy = known
                for bit in pool[:slots]:
                    enemy |= bit
                deck = [bottom, *pool[slots:]] if deck_count else []
                leaf = None
                if exact_leaves and budget > 0:
                    live = u.unpack(mine | enemy | table_mask | sum(deck))
                    leaf = EndgameSolver(live, self._trump_card, self.leaf_nodes, 0)
                # Half the worlds defend selectively, like Smart Runner's
                # continuation styles; all candidates share each world's style.
                careful = 3 if done % 2 else 0
                for index in active:
                    candidate = candidates[index]
                    score = None
                    if phase == 'move' and candidate:
                        # Expect the opponent's reply to our attack exactly:
                        # score both branches of their measured defence
                        # probability instead of sampling it noisily.
                        beaters = enemy & u.beaters[candidate.bit_length() - 1]
                        if beaters:
                            card = u.cards[candidate.bit_length() - 1]
                            rate = (self._profile.defence_rate(self.bucket(card))
                                    if beaters & u.plain else self._profile.trump_rate())
                            beat, budget = self._simulate(
                                u, mine, enemy, deck, attacker, table_mask, pending, mode,
                                candidate, rng, leaf, budget, careful, first='beat')
                            take, budget = self._simulate(
                                u, mine, enemy, deck, attacker, table_mask, pending, mode,
                                candidate, rng, leaf, budget, careful, first='take')
                            score = rate * beat + (1 - rate) * take
                    if score is None:
                        score, budget = self._simulate(
                            u, mine, enemy, deck, attacker, table_mask, pending, mode,
                            candidate, rng, leaf, budget, careful)
                    results[index].append(score)
            active = self._prune(active, results)
        best, leader, means = self._select(active, results, costs)
        info.update(strategy='simulation', worlds=done,
                    selection='score' if best == leader else 'thrift',
                    score_leader=list(map(str, u.unpack(candidates[leader]))),
                    candidates=[{'cards': list(map(str, u.unpack(c))),
                                 'score': round(means[i], 4), 'worlds': len(results[i]),
                                 'thrust_cost': costs[i]}
                                for i, c in enumerate(candidates)])
        return u.unpack(candidates[best])

    def _simulate(self, u, mine, enemy, deck, attacker, table, pending, mode,
                  candidate, rng, leaf, budget, careful, first=None):
        """One candidate in one world: the profiled stand-in, then the rollout.

        ``first`` forces the opponent's first defence to 'beat' or 'take',
        for the split-expectation of an attack; the stand-in drives the rest.
        """
        hands = [mine, enemy]
        remaining = deck[:]
        quota = [self.horizon]
        forced = [first]

        def stand_in(un, their_hands, their_deck, their_attacker, their_table,
                     their_pending, their_mode):
            mover = 1 - their_attacker if their_mode == RESPOND else their_attacker
            if mover != 1 or not quota[0]:
                return None
            quota[0] -= 1
            if forced[0] is not None and their_mode == RESPOND:
                branch, forced[0] = forced[0], None
                beaters = their_hands[1] & un.beaters[their_pending.bit_length() - 1]
                if branch == 'take' or not beaters:
                    return 0
                return self._beat_choice(un, beaters)
            return self._imitate(un, their_hands, their_deck, their_mode, their_table,
                                 their_pending, rng)

        winner = rollout(u, hands, remaining, attacker, table, pending, mode,
                         forced=candidate, policy=stand_in,
                         stop_at_empty=leaf is not None, careful=careful)
        if winner < STOPPED:
            return (winner == 0) - (winner == 1), budget
        next_attacker = winner - STOPPED
        if leaf is not None:
            try:
                outcome = leaf.solve(u.unpack(hands[next_attacker]),
                                     u.unpack(hands[1 - next_attacker])).outcome
            except SearchLimitReached:
                winner = rollout(u, hands, [], next_attacker, 0, 0, MOVE, careful=careful)
            else:
                winner = (DRAW if outcome == 0 else
                          next_attacker if outcome == 1 else 1 - next_attacker)
            budget -= leaf.nodes
        else:
            winner = rollout(u, hands, [], next_attacker, 0, 0, MOVE, careful=careful)
        return (winner == 0) - (winner == 1), budget

    @staticmethod
    def _beat_choice(u, beaters):
        """The stand-in's defence card: cheapest plain beater, else lowest trump."""
        choices = (beaters & u.plain) or beaters
        return choices & -choices

    def _imitate(self, u, hands, deck, mode, table, pending, rng):
        """The opponent's stand-in: their measured habits, cheapest cards first."""
        profile = self._profile
        hand = hands[1]
        if mode == RESPOND:
            beaters = hand & u.beaters[pending.bit_length() - 1]
            if not beaters:
                return 0
            if beaters & u.plain:
                rate = profile.defence_rate(self.bucket(u.cards[pending.bit_length() - 1]))
            else:
                rate = profile.trump_rate()
            return self._beat_choice(u, beaters) if rng.random() < rate else 0
        if mode == MOVE:
            if not table:
                plains, trumps = hand & u.plain, hand & u.trumps
                if plains and rng.random() < profile.lead_trump_rate():
                    choices = trumps or plains
                else:
                    choices = plains or trumps
                return choices & -choices
            eligible = hand & u.ranks(table)
            if deck:
                eligible &= u.plain
            if not eligible or rng.random() >= profile.continue_rate():
                return 0
            return eligible & -eligible
        eligible = hand & u.ranks(table) & u.plain if deck else hand & u.ranks(table)
        cap = max(0, hands[0].bit_count() - 1)
        # Observations are normalized by defender capacity, not by matching
        # cards available. Apply that same denominator, then enforce availability.
        count = min(eligible.bit_count(), cap, round(profile.throwin_share() * cap))
        given = 0
        for _ in range(count):
            low = eligible & -eligible
            eligible ^= low
            given |= low
        return given

    def _prune(self, active, results):
        """Two-stage racing: drop candidates clearly behind on the shared worlds."""
        if len(active) < 2:
            return active
        n = len(results[active[0]])
        if n < 2:
            return active
        leader = max(active, key=lambda i: (sum(results[i]), -i))
        keep = []
        for index in active:
            if index == leader:
                keep.append(index)
                continue
            diffs = [a - b for a, b in zip(results[leader], results[index])]
            mean = sum(diffs) / n
            var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
            if mean > 0.3 and mean * mean * n > 6.5 * var:
                continue
            keep.append(index)
        return keep

    def _select(self, active, results, costs):
        """Lead by score; among statistical ties, keep the useful cards."""
        means = [sum(r) / len(r) if r else 0.0 for r in results]
        leader = max(active, key=lambda i: (means[i], -i))
        close = [leader]
        for index in active:
            if index == leader:
                continue
            diffs = [a - b for a, b in zip(results[leader], results[index])]
            n = len(diffs)
            gap = sum(diffs) / n
            se = sqrt(sum((d - gap) ** 2 for d in diffs) / (n * (n - 1))) if n > 1 else 0.0
            if gap <= min(0.03, 1.5 * se):
                close.append(index)
        chosen = min(close, key=lambda i: (costs[i], -means[i], i))
        return chosen, leader, means


def main():
    parser = argparse.ArgumentParser(description='Puppeteer Durak engine (stdin/stdout protocol)')
    parser.add_argument('--worlds', type=int, default=1024,
                        help='maximum sampled worlds per middlegame decision (default: 1024)')
    parser.add_argument('--probe', type=int, default=96,
                        help='worlds before clearly worse candidates are dropped (default: 96)')
    parser.add_argument('--horizon', type=int, default=2,
                        help='opponent decisions driven by the profile per rollout (default: 2)')
    parser.add_argument('--max-cards', type=int, default=36,
                        help='maximum live cards for the exact endgame (default: 36)')
    parser.add_argument('--max-nodes', type=int, default=500_000,
                        help='exact endgame positions per decision (default: 500000; 0: unlimited)')
    parser.add_argument('--swindle-depth', type=int, default=3,
                        help='random opponent replies used to break ties in lost/drawn endgames '
                             '(default: 3; 0: off)')
    parser.add_argument('--leaf-deck', type=int, default=4,
                        help='score rollouts exactly once the deck has at most this many '
                             'cards (default: 4; 0: off)')
    args = parser.parse_args()
    try:
        engine = PuppeteerEngine(args.worlds, args.probe, args.horizon,
                                 max_cards=args.max_cards,
                                 max_nodes=args.max_nodes or None,
                                 swindle_depth=args.swindle_depth,
                                 leaf_deck=args.leaf_deck)
    except ValueError as error:
        parser.error(str(error))
    engine.run()


if __name__ == '__main__':
    main()
