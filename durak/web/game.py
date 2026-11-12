"""Browser-independent play flow, following gui/frames/play.py."""
from pathlib import Path

from durak.controller import GameController
from durak.engine.dummy import DummyEngine
from durak.engine.nextgen import NextGenEngine
from durak.engine.puppeteer import PuppeteerEngine
from durak.engine.smart_runner import SmartRunnerEngine
from durak.gamelogger.logger import new_log_filename
from durak.engine.wrapper import EngineWrapper
from durak.utils.cards import CardSet, DurakCard


class StalePosition(ValueError):
    pass


class BrowserGame:
    def __init__(self, engine='nextgen', log_dir=None):
        self.log_dir = log_dir
        self.log_filename = None
        self.engines = {
            'nextgen': ('NextGen', 'Strategic play and exact endgames.', NextGenEngine),
            'smart_runner': ('Smart Runner', 'Monte Carlo over hidden cards and exact endgames.',
                              SmartRunnerEngine),
            'puppeteer': ('Puppeteer', 'Profiles your habits and exploits them.',
                          PuppeteerEngine),
            'dummy': ('Dummy', 'Simple strategy.', DummyEngine),
        }
        self.default_engine = engine
        if engine not in self.engines:
            self.default_engine = 'custom'
            path = str(Path(engine).expanduser())
            self.engines['custom'] = (Path(path).name, 'External engine.',
                                      lambda: EngineWrapper(path))
        self.controller = GameController('You', 'Engine')
        self.controller._logger_enabled = False
        self.engine = None
        self.engine_id = self.default_engine
        self.started = False
        self.game_number = 0
        self.revision = 0
        self.history = []
        self.scores = {'you': 0, 'opponent': 0, 'draw': 0}
        self.error = None

    def close(self, reason='closed'):
        if self.engine is not None and self.started and not self.controller.is_game_over():
            self.controller.save_log(reason=reason)
        engine, self.engine = self.engine, None
        if isinstance(engine, EngineWrapper):
            engine.game_end()

    def start(self, engine_id=None):
        engine_id = self.engine_id if engine_id is None else engine_id
        if engine_id not in self.engines:
            raise ValueError('Choose an available engine.')
        self.close(reason='new_deal')
        self.started = False
        self.error = None
        self.engine_id = engine_id
        try:
            self.log_filename = new_log_filename(self.log_dir) if self.log_dir is not None else None
            self.controller._log_filename = self.log_filename
            self.controller._overwrite_log = True
            self.controller._logger_enabled = self.log_filename is not None
            self.controller._player2.name = self.engines[engine_id][0]
            self.engine = self.engines[engine_id][2]()
            if isinstance(self.engine, (NextGenEngine, SmartRunnerEngine, PuppeteerEngine)):
                self.engine.explain_decisions = self.log_filename is not None
            data = self.controller.start_new_game(ignore_winner=False)
            self.trump = data['trump']
            self.hand = CardSet(data['player1_cards'], self.trump)
            self.engine.init(self.trump)
            self.engine.deal(data['player2_cards'], self.controller.get_game_data_for('player2'))
        except Exception:
            self.close(reason='initialization_error')
            raise
        self.started = True
        self.game_number += 1
        self.given_more = []
        self.taking = False
        self.history = []
        self._scored = False
        self._record('New deal. ' + ('You start.' if self.controller.is_player1_to_move()
                                    else self.engines[engine_id][0] + ' starts.'))
        self.revision += 1
        if self.log_filename is not None:
            print('Game log: {}'.format(self.log_filename), flush=True)
        return self.snapshot()

    @property
    def human_turn(self):
        if not self.started or self.error or self.controller.is_game_over():
            return False
        if self.controller.state == self.controller.States.DEALING:
            return False
        return self.controller.is_player1_to_move() != (
            self.controller.state == self.controller.States.RESPONDING)

    def check_revision(self, revision):
        if type(revision) is not int or revision != self.revision:
            raise StalePosition('The table has changed. Please try again.')

    def _record(self, text, cards=()):
        self.history.append({'text': text, 'cards': list(map(str, cards))})
        self.history = self.history[-40:]

    def _register(self, action, cards, human):
        controller = self.controller
        analysis = None if human else getattr(self.engine, 'last_decision', None)
        actor = 'You' if human else self.engines[self.engine_id][0]
        if action == 'play':
            if len(cards) != 1:
                raise ValueError('Choose one card.')
            if controller.state == controller.States.MOVING:
                controller.register_move(cards[0], analysis=analysis)
                self._record(actor + (' attack.' if human else ' attacks.'), cards)
            elif controller.state == controller.States.RESPONDING:
                controller.register_response(cards[0], analysis=analysis)
                self._record(actor + (' defend.' if human else ' defends.'), cards)
            else:
                raise ValueError('Select your throw-ins, then choose Done.')
        elif action == 'take' and controller.state == controller.States.RESPONDING:
            if cards:
                raise ValueError('Taking does not play a card.')
            controller.register_response(None, analysis=analysis)
            self.taking = True
            self._record(actor + (' take the cards.' if human else ' takes the cards.'))
        elif action == 'finish' and controller.state == controller.States.MOVING:
            if cards:
                raise ValueError('Ending an attack does not play a card.')
            controller.register_move(None, analysis=analysis)
            self._record(actor + (' end the attack.' if human else ' ends the attack.'))
        elif action == 'throw' and controller.state == controller.States.GIVING_MORE:
            if len(set(cards)) != len(cards):
                raise ValueError('A card can only be thrown once.')
            controller.register_give_more(cards, analysis=analysis)
            self.given_more = cards[:]
            self._record(actor + ((' throw in.' if human else ' throws in.') if cards
                                  else (' finish the attack.' if human else ' finishes the attack.')), cards)
        else:
            raise ValueError('That action is not available now.')
        if human:
            self.hand.difference_update(cards)
        self._changed()

    def action(self, action, cards, revision):
        self.check_revision(revision)
        if not self.human_turn:
            raise ValueError('Wait for your turn.')
        if not isinstance(cards, list) or any(not isinstance(card, str) for card in cards):
            raise ValueError('Cards must be a list of card names.')
        self._register(action, list(map(DurakCard, cards)), human=True)
        return self.snapshot()

    def step(self, revision):
        """Advance one automatic action so the browser can show each play."""
        self.check_revision(revision)
        if not self.started or self.error or self.controller.is_game_over() or self.human_turn:
            return self.snapshot()
        controller = self.controller
        if controller.state == controller.States.DEALING:
            dealt = controller.deal()
            self.hand.update(dealt['player1_cards'])
            self.engine.deal(dealt['player2_cards'], controller.get_game_data_for('player2'))
            self._record('Cards collected.' if self.taking else 'Table cleared.')
            self.given_more = []
            self.taking = False
            self._changed()
        else:
            phase = {controller.States.MOVING: 'move',
                     controller.States.RESPONDING: 'respond',
                     controller.States.GIVING_MORE: 'give_more'}[controller.state]
            output = getattr(self.engine, phase)(controller.on_table,
                                                controller.get_game_data_for('player2'))
            if output is None:
                cards = []
            elif isinstance(output, str):
                cards = list(map(DurakCard, output.split()))
            elif isinstance(output, DurakCard):
                cards = [output]
            else:
                cards = list(output)
            action = ('throw' if phase == 'give_more' else 'play' if cards
                      else 'take' if phase == 'respond' else 'finish')
            self._register(action, cards, human=False)
        return self.snapshot()

    def _changed(self):
        self.revision += 1
        if self.controller.is_game_over() and not self._scored:
            winner = self._winner()
            self.scores[winner] += 1
            self._scored = True
            self._record({'you': 'You win.', 'opponent': self.engines[self.engine_id][0] + ' wins.',
                          'draw': 'Draw.'}[winner])
            self.close()

    def _winner(self):
        return {'player1': 'you', 'player2': 'opponent', None: 'draw'}[self.controller.winner]

    def fail(self, error):
        self.error = 'The engine stopped: ' + str(error)
        self.revision += 1
        self.close(reason='engine_error')

    def snapshot(self):
        base = {'revision': self.revision, 'started': self.started, 'engine': self.engine_id,
                'game_number': self.game_number,
                'engines': [{'id': key, 'name': value[0], 'description': value[1]}
                            for key, value in self.engines.items()],
                'scores': self.scores.copy(), 'error': self.error}
        if not self.started:
            return base
        controller = self.controller
        data = controller.get_game_data_for('player1')
        phase = controller.state
        legal, actions, limit = [], [], 0
        if self.human_turn:
            if phase == controller.States.RESPONDING:
                legal = self.hand.cards_that_can_beat(controller.on_table[-1])
                actions = ['take']
            else:
                legal = self.hand.cards_that_can_be_added_to(controller.on_table)
                if phase == controller.States.GIVING_MORE:
                    limit = max(0, data['enemy_count'] - 1)
                    legal = legal if limit else []
                    actions = ['throw']
                elif controller.on_table:
                    actions = ['finish']
        base.update(hand=list(map(str, self.hand.sorted_cards())), opponent_count=data['enemy_count'],
                    on_table=data['on_table'], given_more=list(map(str, self.given_more)),
                    trump=str(self.trump), deck_count=data['deck_count'], discarded_count=len(data['discarded']),
                    phase=phase, human_turn=self.human_turn, game_over=controller.is_game_over(),
                    winner=self._winner() if controller.is_game_over() else None,
                    legal_cards=list(map(str, legal)), actions=actions, max_throw=limit,
                    history=self.history[:], taking=self.taking)
        return base
