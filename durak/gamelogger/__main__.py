"""Inspect the same game logs used by the wx viewer, without starting a GUI."""
import argparse
import json

from durak.gamelogger import LogViewer


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file')
    parser.add_argument('--game', type=int, default=1, help='game number in the file (default: 1)')
    parser.add_argument('--action', type=int, help='show full details for one action (1-based)')
    args = parser.parse_args(argv)
    try:
        viewer = LogViewer(args.file)
        index = list(viewer.iterindex())
        if not 1 <= args.game <= len(index):
            raise ValueError('Game must be between 1 and {}'.format(len(index)))
        viewer.load_game(args.game - 1)
        if args.action is not None:
            if not 1 <= args.action <= len(viewer.actions):
                raise ValueError('Action must be between 1 and {}'.format(len(viewer.actions)))
            print(json.dumps(viewer.actions[args.action - 1], indent=2, sort_keys=True))
        else:
            print(index[args.game - 1]['title'])
            if not viewer.actions:
                print('This older log has replay data but no per-action diagnostics.')
            for number, action in enumerate(viewer.actions, 1):
                empty = {'move': 'stop', 'respond': 'take', 'give_more': 'nothing'}
                print('#{} {} {}: {} (deck={})'.format(
                    number, action['player'], action['phase'],
                    ' '.join(action['cards']) or empty[action['phase']], action['gamedata']['deck_count']))
                if action.get('analysis'):
                    print('  ' + action['analysis']['reason'])
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, 'Log error: {}\n'.format(error))


if __name__ == '__main__':
    main()
