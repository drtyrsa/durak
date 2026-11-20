# Durak in your browser

```sh
python3 -m pip install -e .
durak-web
```

The command opens **http://127.0.0.1:8765/** in your default browser. Keep the
terminal running; Ctrl+C closes the server and any external engine process.
Python 3.10+ and a modern browser are sufficient. The game runs offline.

From a source checkout, without installation:

```sh
python3 -m durak.web
```

## Options

```sh
durak-web --engine dummy
durak-web --engine /path/to/your-engine
durak-web --engine "/path/with spaces/engine"
durak-web --port 9000
durak-web --port 0 --no-browser   # choose a free port and print its URL
durak-web --log-dir /path/to/logs
durak-web --no-log
```

`--engine` accepts `nextgen`, `dummy`, or an executable name/path, just like
`durak-play`. External engines use the existing stdin/stdout protocol. Use a
launcher script for engine arguments. The sidebar's opponent selector offers
the two built-ins plus the custom engine supplied on the command line; engine
paths cannot be supplied by HTTP requests.

## Playing

- Click a highlighted card to attack or defend. Gold diamonds mark trumps.
- **Take cards** concedes a defence. The opponent can throw matching cards in.
- **End attack** clears a successfully defended table and exchanges roles.
- When the opponent takes, click matching cards to select your throw-ins,
  then **Done**. Click a selected card again to undo it. The table shows how
  many more cards you can add.
- **New game** immediately starts a new game with the current opponent.
  The previous winner goes first. The first game and games following a draw
  use the normal first-player rule.
- Change **Opponent** in the sidebar to start a new game against another
  engine. Your browser remembers that choice for the next time you launch
  `durak-web` on the same address and port. An explicit `--engine` takes
  precedence for that launch.
- **Rules** opens the rules. The game-end dialog offers a
  rematch or lets you review the final table.
- **Luck balance** appears after the game, in the result dialog and sidebar.
  Its percentile compares your card luck with fixed reference games: **Very
  lucky — top 5%**, for example, is not a 95% chance of winning.
  Expand **Why?** for starting hands, draws, trumps, high cards, cheap answers,
  pairs and suit coverage. Winning despite worse estimated luck is highlighted.
  [How luck is measured and used in engine comparisons](luck.md).

Opponent plays and table clearing are displayed as separate steps. The
opponent's cards remain hidden.
Narrow screens can scroll large hands horizontally; cards also support normal
keyboard focus and activation. Reduced-motion preferences are respected.

Refreshing resumes the table. All tabs using the same server share one game;
stale actions are rejected rather than applied to a changed position. Scores
and recent moves last for the current server process. Restarting the server
resets them. This is a local human-versus-engine game, not network multiplayer.

## Saved games and analysis

Choose **Replay** at the table, then open or drop a saved log. **Replay this
game** in the result dialog opens the game you just finished when its log
was saved. **Table** returns to play.

Both hands are visible. Select a move, drag the position slider, or use the
arrow keys to step through the game. Home and End jump to either end. **Play**
advances automatically. The board shows the position after the selected
action. Round starts show the newly dealt hands. Selecting an engine decision
shows its recorded explanation and candidate scores when available.

For a log containing several games, use **Game in file** to switch. Older
logs support card-by-card replay from their round records. Interrupted games
end at the last recorded position. Files opened or dropped are read locally
by the browser.

`durak-web` automatically saves each game under `./logs/` and prints the file
path in the terminal. Built-in and external engines use the same
**GameLogger format**. Snapshots are updated after every
accepted action. New games and server shutdown preserve unfinished games as
interrupted games, without recording a false draw. Each new game gets its own
file. `--no-log` disables saving; `--log-dir` changes the directory.

The usual deck, hands, table and throw-in replay data is preserved. Additional
`actions` entries record the acting player, hand and public information before
each action, including explicit takes and passes. Built-in NextGen also attaches
its candidate scores, card estimates, strategy and exact-search result when
available. Other engines still produce full game logs; explanations are
optional metadata, not a requirement of the engine protocol.

Inspect the same files without a GUI:

```sh
python3 -m durak.gamelogger logs/your-game.log
python3 -m durak.gamelogger logs/your-game.log --action 17
python3 -m durak.gamelogger logs/your-game.log --luck
```

The first command lists all actions; the second prints the full recorded
position and any engine explanation. The live game state hides the opponent’s
cards. Once the game ends, the replay link serves that game's saved log.

## Implementation

- `durak/web/game.py` manages the turn flow and delegates rules and card
  validation to `GameController` and
  `CardSet`. It uses the same engine protocol through `EngineWrapper` for
  custom engines, and the built-in engines directly.
- `durak/web/server.py` serves the page and JSON API with the standard library's
  `ThreadingHTTPServer`. It binds only to loopback, serializes game mutations,
  and checks request origins, local hostnames, mutation tokens, and revisions.
  Only allowlisted static assets are served. It is intended for local use.
- `durak/web/static/` contains the offline HTML, CSS, and JavaScript. The ivory
  card faces, suit pips, court cards, and patterned backs are drawn with CSS
  and text glyphs so they scale with the table.

Run the headless tests with:

```sh
python3 -m pytest
```

The web tests include full games, card conservation, attacks and defences,
pickups, throw-in limits, last-card draws, engine lifecycle, revision handling,
and real HTTP requests. The HTTP tests bind temporary loopback ports.

The luck display's JavaScript tests also run from pytest when Node.js is
available, or directly with `node --test durak/web/test_luck_display.cjs`.
Node.js remains optional and is not needed to run the game.
