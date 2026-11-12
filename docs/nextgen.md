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

`--engine` accepts the built-in names `nextgen` (the default), `smart_runner` and `dummy`, or
an executable name/path for any engine speaking the pyDurak protocol. Quote
paths containing spaces. An external engine runs as a subprocess and is
stopped when the game ends, on quit/EOF, or on error. To supply engine options,
use an executable launcher script; the path is not interpreted as a shell
command. Built-in engines continue to work directly from the source tree.

The engine speaks the same six-command protocol as DummyEngine. Its stdout
contains only protocol responses, and EOF exits cleanly. GUI support is an
optional install: `pip install -e '.[gui]'`. Existing GUI users can add
`durak-nextgen` through the engine-selection dialog.

## Analytic exchange policy

NextGen now evaluates the **hands left after an exchange**, including the refill,
and searches a short continuation of the current bout. This is a separate
implementation from Smart Runner: it does not import its simulator, sample
hidden hands, or roll out complete games. It uses only the standard library.
The existing exact endgame solver is unchanged.

The hypotheses behind the assessment are:

- **Keep useful defensive capacity.** A fractional matching assigns defenders
  to attacks, with at most one card's worth of capacity per defender. An ace
  cannot be counted as the answer to three separate attacks. Plain suits are
  matched first, then trump attacks, then spare trumps against plain attacks.
  Cover spread across several plain suits earns a small additional bonus.
- **Protect control, especially top trumps.** Cards have a resource value based
  on rank, remaining lower cards in plain suits, and the number of higher live
  trumps. A trump's control premium increases as higher trumps disappear.
- **Count both sides of a gift.** Giving an ace away removes it from our hand
  and adds it to the opponent's resources. A pickup is not automatically an
  opportunity to throw every matching card. Our throw-ins grow greedily only
  while the projected exchange improves; passing is always evaluated.
- **Make card burden matter more near the finish.** Large hands become more
  costly as the stock shrinks. Taking competes with every legal defence, rather
  than being forbidden whenever a beating card exists.
- **Account for the draw order and initiative.** Each leaf projects refill
  counts, which player receives the face-up trump, and who attacks next. It
  follows this controller's rules: the original attacker draws first after a
  successful defence, but the defender draws first after a pickup.

`hand_value.py` contains the hand assessment; `exchange.py` contains the bout
search and refill projection. The score sums resource difference, hand burden,
defensive coverage, suit cover and initiative. These weights express strategic
hypotheses, not solved game values or win probabilities.

Every legal root attack and defence is scored, as are taking and stopping when
legal. After our attack, all possible first beating cards are considered, along
with a voluntary enemy pickup. Search extends through one further attack: up to
four cheap unknown replies plus every known reply, and up to three of our own
matching follow-ups. For our pickup, all legal subsets of up to four shortlisted
matching enemy cards are considered, weighted by exact hypergeometric presence
probabilities. The opponent is modeled as choosing the worst available option
for us. This does not assume that taking proves an inability to defend.

Leaves use analytic marginal card weights after the refill. This keeps decisions
fast and deterministic, but assessing a fractional hand is **not** the same as
averaging assessments of every possible real hand. Dependencies between cards,
longer combinations, omitted follow-ups and opponents with different preferences
remain limitations. The policy also handles larger empty-stock positions if the
exact solver reaches its card or node limit; those decisions are marked `smart`,
not `exact`.

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

### Headless comparison

`durak.engine.matchup` uses the real controller and the normal engine methods,
checks legality, hand synchronization and remembered cards, and plays every
seeded deal twice with the engine seats swapped:

```sh
python3 -m durak.engine.matchup --engine nextgen --opponent smart_runner --pairs 50 --seed 120000
python3 -m durak.engine.matchup --engine nextgen --opponent dummy --pairs 100 --seed 130000
```

Reports include ordinary and luck-adjusted scores, uncertainty over independent
deals, and Elo-style performance differences. [Luck model and interpretation](luck.md).

The analytic exchange policy was developed on deals 100000–100099, with an
initial Smart Runner check on 101000–101019. The final policy was then tested on
separate deals, using default settings for every engine:

| Opponent | Deal seeds | Games | NextGen wins | Losses | Draws | Score (draw = half) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Frozen old NextGen | 110000–110499 | 1,000 | 593 | 373 | 34 | 61.0% |
| Smart Runner | 120000–120049 | 100 | 44 | 51 | 5 | 46.5% |

The old NextGen was frozen from commit
`0a4c03ace6d7aba5e469fb84830d7d281282f768`, including its original middlegame
policy. Both NextGen versions used the same exact solver, 12-card threshold,
500,000-node budget and swindle depth 3. The new policy also replaces Dummy as
the fallback when exact search exceeds its budget. Smart Runner used its default
2,048 worlds and policy revision 3; its implementation was not modified.

This is evidence of improvement over old NextGen, **not** evidence that it is
stronger than Smart Runner. In these concurrent benchmark runs on CPython 3.12,
NextGen's stock-present decisions took roughly 6–7 ms median and 42–43 ms at the
95th percentile; the slowest was 203 ms. Exact searches have a separate budget.
Timings depend on the machine and concurrent load.

The existing `--opponent previous` benchmark name still means **Dummy middlegame
plus the exact solver**, not the frozen old smart policy in the table above.
`durak-nextgen --middlegame dummy` retains that original baseline. The default
`smart` option now selects the analytic exchange policy; terminal, web, autoplay
and GUI clients receive it through the unchanged protocol.

Tests independently check defensive matching against exhaustive assignments,
refill marginals against every hidden allocation in small controller positions,
reply probabilities, joint throw-ins, public-information boundaries, hash-seed
stability, and complete games. Regression positions cover saving big trumps,
retaining aces during an enemy pickup, spending a cheap trump when appropriate,
and preserving useful suit cover.

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
discard pile, remembered cards, candidate scores and belief estimates.
Analytic decisions identify `model: analytic_exchange` and `policy_revision: 1`.
`if_bout_ends_now` breaks an immediate exchange into resource, burden, coverage,
suit-cover and initiative components, including refill counts and `face_up_to`.
Defence candidates also show `continuation_adjustment` for the modeled extra
attack or throw-ins. Attack candidates show `if_enemy_takes` and the planned
`pickup_throw_ins`; that conditional value is not the whole attack score.
The `search` object records the bounds, and `leaf_evaluations` records the work.
Throw-in candidates are the subsets actually evaluated by the greedy search,
including rejected additions, rather than a claim to have scored all subsets.
Exact decisions report the solved outcome and search nodes, plus
`expected_vs_random` when a lost or drawn position needed a tie-break. External engines
use the unchanged card-only protocol, so their logs contain full game/position
data without internal explanations.

Taking is now scored even when a beating card exists. If a high trump defends
a low card, compare its candidate score with the take score and inspect the
refill and continuation terms. Neither a resource premium nor a penalty is an
absolute prohibition. Middlegame scores prefer **higher** values; old logs from
the previous policy used costs where lower was preferred. Each record states
its own `score_convention`.

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
loss. A proven winning choice ends that state's search immediately. Among
winning actions, the first in deterministic move order is played; distance to
victory is not optimized.

### Lost and drawn positions

Minimax is indifferent between actions with the same value, but real opponents
make mistakes. When the player to act cannot force a win, the root action is
chosen among the **exactly optimal** ones by its expected outcome if the
opponent picks uniformly among its legal actions for its next `swindle_depth`
decisions (default 3). Our own decisions inside that lookahead are also
restricted to exactly optimal actions, and positions after it are valued by
exact minimax. The tie-break therefore never changes the solved outcome; it
only prefers losing/drawing lines where more opponent replies are errors.
`swindle_depth=0` (`--swindle-depth 0`) restores the plain move-order choice.

The uniform-reply model is an assumption, not a model of any particular
opponent; throw-ins count every legal subset as one reply. Positions after
opponent mistakes must be solved exactly, so this costs extra nodes. They
count against the same per-decision budget; if it runs out during the
tie-break, the exact default action is played instead of falling back.

Measured on the real controller against Dummy: in 1,000 sampled lost or drawn
five-versus-five endgames (random trumps), the solver side scored 267 wins /
207 draws / 526 losses without the tie-break and 356 / 200 / 444 at depth 3.
In 1,200 complete games on seeds 400–999 (both seats), NextGen's losses fell
from 320 to 274; depth 4 gave 269 and was not worth its extra cost.

### Cache

The cache contains both values and optimal actions and survives subsequent
decisions in the same game, including pickups. It is reset on `init`. This is
an **on-demand in-memory table**, not a downloaded or persistent full tablebase.

With a budget the table holds at most `max_nodes` entries. When a search finds
it full, entries from earlier calls that use a card no longer live (and are
therefore unreachable) are dropped first; if that is not enough, all earlier
entries are dropped. The current call adds fewer entries than its node budget,
so a long-lived solver never fails a search that a fresh solver completes.
(Previously a full table stopped caching altogether, and searches could run out
of budget re-expanding shared subtrees.)

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
positions per decision**, including tie-break work in lost/drawn positions.
The cache also holds at most 500,000 entries (see *Cache* for eviction). These
are work/memory guards, not a wall-clock deadline. Above either limit NextGen
uses the analytic exchange policy, so that decision has no optimality claim.
The explicit `--middlegame dummy` baseline still uses Dummy in this situation.
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
`expected_vs_random` is set only when a lost or drawn position had several
exactly optimal actions; it is the chosen action's expected outcome (−1..1)
under the uniform-reply model. `NextGenEngine.last_solution` is set only for a completed exact search;
otherwise `fallback_reason` explains why exact search was not used (a nonempty
deck normally selects the middlegame policy). The standalone solver has
no default budget and raises `SearchLimitReached` if an explicit budget expires.

The benchmark on this development machine, CPython 3.10, seed 20261110, fixed
spade trump, 200 uniformly sampled six-versus-six deals: all 200 solved; median
about 30 ms / 15,748 new positions, maximum about 760 ms / 340,303 positions.
With `--swindle-depth 0`: median about 3.5 ms / 2,015 positions, maximum about
230 ms / 102,885. These first decisions are the expensive case; later
decisions reuse the cache. These are sample results, not worst-case guarantees.
Run the benchmark command above to measure your machine or larger hands.

Validation includes all 5,040 one-versus-one cases across trump suits,
5,015 independently evaluated controller positions from a six-card universe,
an independent controller-based check of tie-break expectations in move,
respond and give-more positions, cache-pressure regressions,
strategic regressions for voluntary takes, stopping attacks, stronger defences
and trump throw-ins, protocol subprocess tests, complete headless games, and
terminal input handling.
