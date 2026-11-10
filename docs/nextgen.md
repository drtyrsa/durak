# NextGen

NextGen's first component is an exact win/draw/loss endgame solver. While the
deck is nonempty, it uses DummyEngine's existing decisions. Everything below
runs on Python 3.10+ without wxPython or a display server.

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
otherwise `fallback_reason` explains the fallback. The standalone solver has
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
