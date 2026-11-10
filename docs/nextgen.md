# NextGen

NextGen combines a deterministic, public-information middlegame policy with
an exact win/draw/loss endgame solver. Everything below runs on Python 3.10+
without wxPython or a display server. The middlegame is a heuristic, not an
optimal solution of the hidden-information game.

## Run and test

```sh
python3 -m pip install -e .
python3 -m pip install pytest
durak-play                         # human versus NextGen in the terminal
durak-play --engine dummy
durak-play --engine durak-dummy     # any engine executable on PATH
durak-play --engine /path/to/engine # any pyDurak-protocol engine
durak-autoplay durak-nextgen durak-dummy --matches-number=1 --match-size=100
python3 -m pytest --ignore=durak/gui
python3 -m durak.engine.benchmark --samples 200 --hand-size 6
python3 -m durak.engine.matchup --pairs 1000 --seed 10000 --opponent previous
python3 -m durak.engine.matchup --pairs 500 --seed 10000 --opponent dummy
```

Without installing the project, `python3 -m durak.play` starts the terminal
game and `python3 -m durak.engine.nextgen` starts the stdin/stdout engine.
Both use only the standard library. Enter cards such as `7H` or `TS`; Enter
means stop attacking, take, or throw nothing, depending on the prompt.
Throw-ins accept several space-separated cards. `quit` or EOF exits.

`--engine` accepts the built-in names `nextgen` (the default) and `dummy`, or
an executable name/path for any engine speaking the pyDurak protocol. Quote
paths containing spaces. An external engine runs as a subprocess and is
stopped when the game ends, on quit/EOF, or on error. To supply engine options,
use an executable launcher script; the path is not interpreted as a shell
command. Built-in engines continue to work directly from the source tree.

The engine speaks the same six-command protocol as DummyEngine. Its stdout
contains only protocol responses, and EOF exits cleanly. GUI support is an
optional install: `pip install -e '.[gui]'`. Existing GUI users can add
`durak-nextgen` through the engine-selection dialog.

## Middlegame hypotheses

The default policy scores legal attacks and defences using these preferences:

- **Keep trumps and useful suit cover.** Trumps receive a substantial reserve
  value; the strongest card held in each other suit gets a smaller bonus when
  there are still lower cards it could beat. Value also depends on printed rank
  and the number of lower cards still unseen, rather than printed rank alone.
- **Lead from matching ranks.** A pair or triple provides follow-up attacks;
  occasionally leading a seven is better than an isolated six.
- **Apply pressure where a defence is unlikely.** Estimate the chance that the
  opponent can beat an attack in suit, or at all. This is a modest bonus, so it
  does not override the cost of spending a valuable card.
- **Avoid opening an enemy rank.** A defence can expose a new rank for another
  attack. Sometimes playing an eight instead of a seven avoids a known enemy
  seven, or a rank whose remaining cards are likely in the opposing hand.

Optional attacks and throw-ins retain Dummy's conservative rule of keeping
trumps. Defence still spends a cheap trump when needed; it does not preserve
every trump at any cost. A trial rule that voluntarily took small attacks to
save valuable trumps did not improve results consistently and was left out.
The exact solver can still choose voluntary takes and trump throw-ins once
the deck is empty.

### What can the opponent hold?

The engine subtracts its hand, the current table and all discarded cards from
the 36-card deck. While the deck is nonempty, the face-up bottom trump cannot
be in the opponent's hand. It also remembers cards the opponent visibly picks
up, including its own throw-ins, and removes those cards when they are played,
discarded, or received into its own hand. A new game resets this memory. Missing
bout metadata clears uncertain memories instead of inventing a result.

For the remaining unknown opponent slots, the model assumes a uniform sample
from the remaining possible cards. If `m` slots are unknown among `N` possible
cards, of which `k` would beat an attack, the probability of at least one is
`1 - C(N-k, m) / C(N, m)`. A remembered beating card makes that probability one.
The same calculation estimates the risk of opening a matching rank.

This automatically accounts for discarded suits and ranks. If all queens have
gone, the probability of an enemy queen is zero. With just the face-up trump
left in the deck, every other unseen card is certainly in the opposing hand.
The model uses no actual hidden hand or deck order. It does not treat taking as
proof of a missing suit: an opponent may take voluntarily. The uniform prior
does not yet learn opponents' preferences from their choices.

### Reproduce the comparison

`durak.engine.matchup` uses the real controller and the normal engine methods,
checks legality, hand synchronization and remembered cards, and plays every
seeded deal twice with the engine seats swapped. The `previous` opponent is
NextGen with Dummy's middlegame **and the same exact solver and search budget**;
this separates middlegame improvements from the existing endgame advantage.

After exploratory trials on seeds 0–99 and validation on 1000–1499, the final
policy was evaluated on separate deals starting at seed 10000:

| Opponent | Games | NextGen wins | Losses | Draws | Score (draw = half) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Previous NextGen | 2,000 | 982 | 908 | 110 | 51.85% |
| Dummy | 1,000 | 622 | 309 | 69 | 65.65% |

The improvement over previous NextGen is modest in this sample; this is a
starting policy, not evidence of universally strong or optimal play. On this
machine with CPython 3.12, the new engine's middlegame decisions took about
0.23–0.25 ms median and at most 1.3 ms in these runs. Exact endgame searches have
their separate budget and timing characteristics below. There are no random
rollouts or new dependencies in the middlegame policy.

For a baseline engine process, run `durak-nextgen --middlegame dummy`, or create
`NextGenEngine(middlegame='dummy')` in Python. The default is `smart`; terminal,
web, autoplay and GUI clients all get it without changing the protocol. The
paired benchmark runs in process, while `durak-autoplay` still exercises actual
engine subprocesses.

## Inspect a questionable move

Logging belongs to `GameController` / `GameLogger`, and works with every engine.
Web play saves games automatically to `logs/`; terminal play can use
`durak-play --log-dir logs` with any opponent. Autoplay retains its existing
`--log-file=matches.log` option. These are the same replay files the wx viewer
opens, extended with per-action position data and optional engine analysis.

```sh
python3 -m durak.gamelogger logs/your-game.log
python3 -m durak.gamelogger logs/your-game.log --action 17
python3 -m durak.gamelogger matches.log --game 2 --action 17
```

Built-in NextGen in web/terminal games with logging enabled supplies the extra
analysis. It records the hand **before** playing, the table, deck/opponent counts,
discard pile, remembered cards, candidate cost components and belief estimates.
Exact decisions report the solved outcome and search nodes. External engines
use the unchanged card-only protocol, so their logs contain full game/position
data without internal explanations.

A high trump defending a low card while six cards remain in the deck is a
useful example of the current policy's limitation: it scores beating cards but
does **not** score voluntarily taking. If an ace trump is the only beating card,
it plays that ace. The log explicitly lists taking as legal but unevaluated;
it does not claim that taking was worse or invent a winning continuation.
Middlegame scores are heuristic costs (lower is preferred), not win chances.

For programmatic inspection, use `NextGenEngine(explain_decisions=True)` and
read `last_decision` after a move. Producing explanations does not change move
selection. The engine itself writes no log files and keeps protocol stdout clean.

## Information and rules

An empty deck really does make this a perfect-information game: the opponent
holds `all 36 cards - own hand - table - discarded`. No private controller data
is used by the engine. Missing or inconsistent game data falls back to Dummy.

The solver follows **this repository's GameController**, including:

- Attacks one card at a time, matching any rank already on the table.
- Same-suit higher cards or trumps beat an attack; taking is always an option.
- The attacker may end a successful defence or continue, including with trumps.
- After a take, every legal subset of matching cards is considered. The limit
  is the defender's *current* hand size minus one, as in `register_give_more`.
- Successful defence discards the table and exchanges roles. A take transfers
  the table and throw-ins to the defender, keeping the same attacker.
- Empty hands end the game immediately under the controller's rules. The
  exception is an attacker's final card against a defender's single beatable
  card: the defender may beat it for a draw. Against multiple remaining cards,
  the attacker's last card wins immediately.

There is no added six-attack cap, repetition rule, or different last-card rule.

## Why exact search terminates

Between bout boundaries, cards move from hands onto the table. At the end of
a bout, either the total number of live cards decreases (a successful defence),
or the attacker stays the same and has strictly fewer cards (a take).
Thus the pair `(live card count, attacker's hand size)` decreases
lexicographically between bouts. Pickups cannot create a cycle.

`EndgameSolver` performs memoized minimax on this acyclic graph. Each state
stores the two hand bit masks, the table bit mask, and the phase/uncovered
attack. Completed pairings and their order do not affect future choices, so
equivalent table orders share a cache entry. Values are exact: win > draw >
loss. A proven winning choice ends that state's search immediately. Equal
outcomes use deterministic move ordering; distance to victory is not optimized.

The cache contains both values and optimal actions and survives subsequent
decisions in the same game, including pickups. It is reset on `init`. This is
an **on-demand in-memory table**, not a downloaded or persistent full tablebase.

With enough memory, work is O(V + E) over visited states and generated actions,
plus mask operations. Memory is O(V). If `n` cards are live, a loose state-count
bound is `(n + 2) * 4**n`: each card can be with either player, on the table, or
discarded, and the phase identifies an uncovered card or one of two attacker
decisions. Most of these assignments are impossible or never visited.
Throw-ins can have exponentially many subsets, so worst-case work remains
exponential even though play cannot cycle.

## How large would global tables be?

Fix one trump suit, label the hands by attacker and defender, and start with an
empty table. Exactly `k` cards per hand gives
`C(36, k) * C(36 - k, k)` hand pairs. The following are direct combinatorial
counts, not measured file sizes. Storage assumes only two packed outcome bits
per entry, with no moves, indexes, distance information, or compression.

| Cards per hand | Hand pairs | Packed outcomes, decimal units |
| --- | ---: | ---: |
| 1 | 1,260 | 315 B |
| 2 | 353,430 | 88.4 KB |
| 3 | 38,955,840 | 9.74 MB |
| 4 | 2,118,223,800 | 529.6 MB |
| 5 | 64,055,087,712 | 16.0 GB |
| 6 | 1,156,550,194,800 | 289.1 GB |

The last row alone is **not a complete twelve-card tablebase**: play also
reaches unequal hands and states with cards on the table. Even just all
nonempty, ordered hands totaling at most twelve cards with an empty table
give `sum(C(36,n) * (2**n - 2), n=2..12) = 6,670,279,054,722` entries,
or about **1.67 TB** at two bits each before symmetry reduction.

All trump suits can be mapped to a fixed suit. Permuting the other three
suits offers up to another factor of six, although symmetric positions need
special handling. Further rank-pattern normalization and compression could
help. Those reductions are not implemented yet.

Generation must at least process the indexed positions and their legal
transitions. Even a hypothetical million entries per second would take about
13.4 days for the six-versus-six row alone, excluding transitions and smaller
or unequal hands. A position-specific table avoids nearly all that work.

## Practical limits and measurements

Defaults: **12 total live cards**, including the table, and **500,000 uncached
positions per decision**. The cache also holds at most 500,000 entries. These
are work/memory guards, not a wall-clock deadline. Above either limit NextGen
uses DummyEngine for that decision, so that decision has no optimality claim.
Later decisions retry as the position becomes smaller or cached work helps.
An interrupted search never records an approximate value as an exact result.

For larger or unrestricted calculations:

```sh
python3 -m durak.engine.nextgen --max-cards 16 --max-nodes 2000000
python3 -m durak.engine.nextgen --max-cards 36 --max-nodes 0
```

Unlimited search can consume substantial time and memory. For autoplay with
custom options, put the command in an executable launcher; EngineWrapper
accepts an executable path, not shell arguments.

For programmatic analysis:

```python
from durak.engine.endgame import EndgameSolver

solver = EndgameSolver(['6C', '8D', '6D', '7C'], trump='6S')
solution = solver.solve(attacker=['6C', '8D'], defender=['6D', '7C'])
assert solution.outcome == 1
assert str(solution.cards[0]) == '8D'  # leading 6C only draws
```

`Solution.outcome` is from the deciding player's perspective; `cards` is the
optimal action (empty for pass/take); `nodes` counts new states in that call.
`NextGenEngine.last_solution` is set only for a completed exact search;
otherwise `fallback_reason` explains why exact search was not used (a nonempty
deck normally selects the middlegame policy). The standalone solver has
no default budget and raises `SearchLimitReached` if an explicit budget expires.

The initial benchmark on this development machine, CPython 3.10, seed
20261110, fixed spade trump, 200 uniformly sampled six-versus-six deals: all
200 solved; median about 4 ms / 2,015 new positions, maximum about 236 ms /
102,885 positions. These are sample results, not worst-case guarantees.
Run the benchmark command above to measure your machine or larger hands.

Validation includes all 5,040 one-versus-one cases across trump suits,
5,015 independently evaluated controller positions from a six-card universe,
strategic regressions for voluntary takes, stopping attacks, stronger defences
and trump throw-ins, protocol subprocess tests, complete headless games, and
terminal input handling.
