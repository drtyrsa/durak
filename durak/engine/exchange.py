"""Bounded, deterministic bout search with analytic hidden-card probabilities.

Leaves are exchanges, refills and hand assessments, not simulated game results.
"""
from math import comb

from durak.engine.hand_value import INDEX, HandAssessment, weights

# Branch bounds apply to card actions, never sampled deals or game rollouts.
REPLY_WIDTH = 4
FOLLOWUP_WIDTH = 3
THROW_WIDTH = 4


class BoutEvaluator:
    def __init__(self, policy):
        self.p = policy
        self.live = frozenset(policy.hand | set(policy.table) | policy.unseen)
        self.bottom = {policy.trump} if policy.deck_count else set()
        self.assessment = HandAssessment(policy.trump, self.live)
        self.settled = {}
        self.gives = {}
        self.give_options = {}
        self.decisions = {}

    def resource(self, card):
        return self.assessment.resources[INDEX[card]]

    def belief(self, hand, table, count, known):
        possible = self.live - hand - set(table) - self.bottom
        known = known & possible
        slots = count - len(known)
        return possible - known if slots else frozenset(), known, slots

    def has(self, cards, hand, table, count, known):
        pool, known, slots = self.belief(hand, table, count, known)
        if known & cards:
            return 1.0
        return 1 - comb(len(pool) - len(pool & cards), slots) / comb(len(pool), slots)

    def enemy_choice(self, default, alternatives, hand, table, count, known):
        """Expected worst available modeled reply, including passing/taking.

        Probabilities of the first available card in this ordering are exact
        under the uniform-hand belief. The leaf values remain approximations.
        """
        seen, previous, value = set(), 0.0, 0.0
        for card, score in sorted(alternatives, key=lambda item: (item[1], item[0])):
            if score >= default:
                break
            seen.add(card)
            probability = self.has(seen, hand, table, count, known)
            value += (probability - previous) * score
            previous = probability
            if previous == 1:
                break
        return value + (1 - previous) * default

    def settle(self, hand, table, count, known, attacking, taken=False, given=()):
        hand, table, known, given = map(frozenset, (hand, table, known, given))
        key = (hand, table, count, known, attacking, taken, given)
        if key in self.settled:
            return self.settled[key]
        live = self.live
        if taken and attacking:
            hand -= given
            known |= table | given
            count += len(table) + len(given)
        elif taken:
            hand |= table | given
            known -= given
            count -= len(given)
        else:
            live -= table
        known -= hand
        known &= live
        # On a defence the attacker refills first; on a pickup the defender
        # refills first. The last draw is the public bottom trump.
        remaining = self.p.deck_count
        draws, bottom = [0, 0], None
        first = 0 if (not attacking if taken else attacking) else 1
        for seat in (first, 1 - first):
            need = max(0, 6 - (len(hand) if seat == 0 else count))
            draws[seat] = min(remaining, need)
            remaining -= draws[seat]
            if draws[seat] and not remaining:
                bottom = seat
        pool = live - hand - known - self.bottom
        slots = count - len(known)
        ours, enemy = weights(hand), weights(known)
        if pool:
            for card in pool:
                i = INDEX[card]
                ours[i] = (draws[0] - (bottom == 0)) / len(pool)
                enemy[i] = (slots + draws[1] - (bottom == 1)) / len(pool)
        if bottom is not None:
            (ours if bottom == 0 else enemy)[INDEX[self.p.trump]] = 1.0
        initiative = 1 if (attacking if taken else not attacking) else -1
        result = self.assessment.evaluate(ours, enemy, remaining, initiative)
        result.update(draws={'ours': draws[0], 'enemy': draws[1],
                             'face_up_to': ('ours' if bottom == 0 else 'enemy')
                             if bottom is not None else None})
        self.settled[key] = result
        return result

    def give(self, hand, table, count, known):
        """Add cards only while the projected exchange improves; keep gifts out."""
        key = (hand, table, count, known)
        if key in self.gives:
            return self.gives[key]
        ranks = {c.rank for c in table}
        legal = {c for c in hand if c.rank in ranks}
        given = frozenset()
        value = self.settle(hand, table, count, known, True, True)['score']
        evaluated = {(): value}
        while legal and len(given) < max(0, count - 1):
            options = [(self.settle(hand, table, count, known, True, True, given | {c})['score'], c)
                       for c in sorted(legal)]
            evaluated.update((tuple(sorted(given | {c})), score) for score, c in options)
            score, card = max(options, key=lambda item: (item[0], -self.resource(item[1]),
                                                       -INDEX[item[1]]))
            if score <= value:
                break
            given |= {card}
            legal.remove(card)
            value = score
        result = value, tuple(sorted(given))
        self.gives[key] = result
        self.give_options[key] = list(evaluated.items())
        return result

    def take(self, hand, table, count, known):
        base = self.settle(hand, table, count, known, False, True)['score']
        if len(hand) <= 1 or not count:
            return base
        pool, certain, slots = self.belief(hand, table, count, known)
        ranks = {c.rank for c in table}
        eligible = sorted((c for c in pool | certain if c.rank in ranks),
                          key=lambda c: (self.resource(c), c))[:THROW_WIDTH]
        # Enumerate presence of a few matching ranks, not complete hidden hands.
        # The opponent may add any legal subset, including nothing. This accounts
        # for several junk cards arriving together instead of assuming one gift.
        subsets = [frozenset(c for i, c in enumerate(eligible) if mask & (1 << i))
                   for mask in range(1 << len(eligible))]
        options = [(given, self.settle(hand, table, count, known, False, True, given)['score'])
                   for given in subsets if len(given) <= len(hand) - 1
                   and len(given - certain) <= slots]
        certain_gifts = certain & set(eligible)
        unknown_gifts = set(eligible) - certain
        denominator = comb(len(pool), slots)
        value = 0.0
        for present in subsets:
            if not certain_gifts <= present:
                continue
            outside = slots - len(present - certain_gifts)
            if not 0 <= outside <= len(pool) - len(unknown_gifts):
                continue
            probability = comb(len(pool) - len(unknown_gifts), outside) / denominator
            value += probability * min(score for given, score in options if given <= present)
        return value

    def beats(self, card, attack):
        return ((card.suit == attack.suit and card > attack)
                or card.suit == self.p.trump.suit != attack.suit)

    def shortlist(self, cards, known):
        ordered = sorted(cards, key=lambda c: (self.resource(c), c))
        return sorted(set(ordered[:REPLY_WIDTH]) | set(c for c in ordered if c in known))

    def attack(self, hand, table, count, known, card, depth):
        hand = hand - {card}
        table = table + (card,)
        take_value = self.give(hand, table, count, known)[0]
        pool, certain, _ = self.belief(hand, table, count, known)
        replies = sorted(c for c in pool | certain if self.beats(c, card))
        deeper = set(self.shortlist(replies, certain))
        values = []
        for reply in replies:
            after = table + (reply,)
            stop = self.settle(hand, after, count - 1, known - {reply}, True)['score']
            if depth and reply in deeper and hand and count > 1:
                ranks = {c.rank for c in after}
                follow = sorted((c for c in hand if c.rank in ranks),
                                key=lambda c: (self.resource(c), c))[:FOLLOWUP_WIDTH]
                stop = max([stop] + [self.attack(hand, after, count - 1, known - {reply}, c, 0)
                                     for c in follow])
            values.append((reply, stop))
        return self.enemy_choice(take_value, values, hand, table, count, known)

    def response(self, hand, table, count, known, depth):
        options = [((), self.take(hand, table, count, known))]
        for card in sorted(c for c in hand if self.beats(c, table[-1])):
            after_hand, after_table = hand - {card}, table + (card,)
            value = self.settle(after_hand, after_table, count, known, False)['score']
            if depth and after_hand and count:
                pool, certain, _ = self.belief(after_hand, after_table, count, known)
                ranks = {c.rank for c in after_table}
                attacks = self.shortlist((c for c in pool | certain if c.rank in ranks), certain)
                replies = [(c, max(score for _, score in self.response(
                    after_hand, after_table + (c,), count - 1, known - {c}, 0))) for c in attacks]
                value = self.enemy_choice(value, replies, after_hand, after_table, count, known)
            options.append(((card,), value))
        return options

    def choose(self, phase):
        if phase in self.decisions:
            return self.decisions[phase][0]
        hand, table = frozenset(self.p.hand), self.p.table
        count, known = self.p.enemy_count, frozenset(self.p.known_enemy)
        if phase == 'respond':
            options = self.response(hand, table, count, known, 1)
        elif phase == 'give_more':
            self.give(hand, table, count, known)
            options = self.give_options[hand, table, count, known]
        else:
            ranks = {c.rank for c in table}
            legal = sorted(c for c in hand if not table or c.rank in ranks)
            options = [((c,), self.attack(hand, table, count, known, c, 1)) for c in legal]
            if table:
                options.append(((), self.settle(hand, table, count, known, True)['score']))
        chosen = max(options, key=lambda item: (item[1], -sum(self.resource(c) for c in item[0])))[0]
        self.decisions[phase] = chosen, options
        return chosen

    def explain(self, phase, chosen):
        self.choose(phase)
        hand, table = frozenset(self.p.hand), self.p.table
        count, known = self.p.enemy_count, frozenset(self.p.known_enemy)
        candidates = []
        for cards, score in self.decisions[phase][1]:
            row = {'action': ('take' if phase == 'respond' and not cards else
                              'stop' if phase == 'move' and not cards else
                              'throw' if phase == 'give_more' else 'play'),
                   'cards': list(map(str, cards)), 'evaluated': True,
                   'selected': tuple(cards) == tuple(chosen), 'score': score}
            if phase == 'respond':
                immediate = self.settle(hand - set(cards), table + cards, count, known,
                                        False, taken=not cards)
                row.update(if_bout_ends_now=immediate,
                           continuation_adjustment=score - immediate['score'])
            elif phase == 'move' and cards:
                after_hand, after_table = hand - set(cards), table + cards
                _, given = self.give(after_hand, after_table, count, known)
                row.update(if_enemy_takes=self.settle(after_hand, after_table, count, known,
                                                     True, True, given),
                           pickup_throw_ins=list(map(str, given)))
            else:
                row['if_bout_ends_now'] = self.settle(hand, table, count, known, True,
                                                     phase == 'give_more', cards)
            candidates.append(row)
        return {'reason': 'Best modeled exchange after short bout search and analytic refills.',
                'score_convention': 'higher is preferred; hand assessments, not win probabilities',
                'model': 'analytic_exchange', 'policy_revision': 1,
                'leaf_evaluations': len(self.settled), 'candidates': candidates,
                'search': {'further_attacks': 1, 'all_first_defences': True,
                           'reply_width': REPLY_WIDTH,
                           'include_known_replies': True, 'own_followup_width': FOLLOWUP_WIDTH,
                           'enemy_throw_width': THROW_WIDTH,
                           'own_throw_subsets': 'greedy improving additions'}}
