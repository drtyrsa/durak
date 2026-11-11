"""Play Durak against a configurable engine in a terminal, without wxPython."""
import argparse
import os.path

from durak.controller import GameController
from durak.controller.exceptions import GameControllerError
from durak.engine.dummy import DummyEngine
from durak.engine.nextgen import NextGenEngine
from durak.engine.smart_runner import SmartRunnerEngine
from durak.gamelogger.logger import new_log_filename
from durak.engine.wrapper import EngineWrapper, EngineWrapperException
from durak.utils.cards import DurakCard


def play(engine, read=input, write=print, controller=None):
    """Run one human (player 1) versus engine (player 2) game."""
    controller = controller or GameController('You', type(engine).__name__)
    data = controller.start_new_game()
    engine.init(data['trump'])
    engine.deal(data['player2_cards'], controller.get_game_data_for(controller.PLAYER2))
    hand = set(data['player1_cards'])
    write('Cards: 6 7 8 9 T J Q K A; suits: C D H S. Example: 7H.')
    write('Press Enter to stop attacking / take / throw nothing. Type quit to leave.')

    try:
        while not controller.is_game_over():
            state = controller.state
            if state == controller.States.DEALING:
                dealt = controller.deal()
                hand.update(dealt['player1_cards'])
                engine.deal(dealt['player2_cards'],
                            controller.get_game_data_for(controller.PLAYER2))
                continue

            human = controller.is_player1_to_move()
            if state == controller.States.RESPONDING:
                human = not human
            phase, prompt, register = {
                controller.States.MOVING: ('move', 'Attack', controller.register_move),
                controller.States.RESPONDING: ('respond', 'Defend', controller.register_response),
                controller.States.GIVING_MORE: ('give_more', 'Throw cards', controller.register_give_more),
            }[state]
            if human:
                write('\nTrump: {} | Deck: {} | Opponent: {} cards'.format(
                    data['trump'], controller.deck_count,
                    controller.get_game_data_for(controller.PLAYER1)['enemy_count']))
                write('Your hand: ' + ' '.join(map(str, sorted(hand))))
                write('Table: ' + (' '.join(map(str, controller.on_table)) or '(empty)'))
                text = read(prompt + '> ').strip().upper()
                if text in ('QUIT', 'EXIT'):
                    write('Game ended.')
                    return None
            else:
                output = getattr(engine, phase)(
                    controller.on_table,
                    controller.get_game_data_for(controller.PLAYER2))
                # In-process engines return protocol text; EngineWrapper
                # returns cards (a list for give_more) or None for a pass.
                if phase == 'give_more' and output is not None and not isinstance(output, str):
                    text = ' '.join(map(str, output))
                else:
                    text = '' if output is None else str(output)

            try:
                cards = list(map(DurakCard, text.split()))
                if phase != 'give_more' and len(cards) > 1:
                    raise ValueError('Enter one card at a time.')
                register(cards if phase == 'give_more' else (cards[0] if cards else None),
                         analysis=None if human else getattr(engine, 'last_decision', None))
            except (ValueError, GameControllerError) as error:
                if not human:
                    raise
                write('Invalid action: ' + (str(error) or 'A card is required.'))
                continue
            if human:
                hand.difference_update(cards)
            else:
                empty_action = {'move': 'stop', 'respond': 'take', 'give_more': 'nothing'}
                write('Opponent {}: {}'.format(phase, text or empty_action[phase]))
    except (EOFError, KeyboardInterrupt):
        write('\nGame ended.')
        return None

    write({controller.PLAYER1: 'You win!', controller.PLAYER2: 'Opponent wins!',
           None: 'Draw!'}[controller.winner])
    return controller.winner


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', default='nextgen', metavar='NAME_OR_PATH',
                        help='nextgen (default), smart_runner, dummy, or an engine executable name/path')
    parser.add_argument('--log-dir', help='save this game for replay, with any engine')
    args = parser.parse_args(argv)
    builtins = {'nextgen': NextGenEngine, 'smart_runner': SmartRunnerEngine, 'dummy': DummyEngine}
    external = args.engine not in builtins
    engine = None
    controller = None
    try:
        engine = (EngineWrapper(os.path.expanduser(args.engine)) if external
                  else builtins[args.engine]())
        if args.log_dir:
            filename = new_log_filename(args.log_dir)
            controller = GameController('You', args.engine, log_filename=filename, overwrite_log=True)
            if hasattr(engine, 'explain_decisions'):
                engine.explain_decisions = True
            print('Game log: {}'.format(filename))
            play(engine, controller=controller)
        else:
            play(engine)
    except (OSError, EngineWrapperException, GameControllerError, ValueError) as error:
        parser.exit(1, 'Engine error: {}\n'.format(error))
    finally:
        if controller is not None and not controller.is_game_over():
            controller.save_log(reason='closed')
        if external and engine is not None:
            engine.game_end()


if __name__ == '__main__':
    main()
