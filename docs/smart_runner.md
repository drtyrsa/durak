# Smart Runner

Smart Runner plays the middlegame (cards left in the deck) by determinized
Monte Carlo search, and the endgame (empty deck) with the same exact
`EndgameSolver` as NextGen. It is pure Python, like the rest of the project.

```sh
durak-play --engine smart_runner
durak-web            # choose "Smart Runner" as the opponent
durak-smart-runner   # stdin/stdout protocol engine (python3 -m durak.engine.smart_runner)
python3 -m durak.engine.matchup --engine smart_runner --opponent nextgen --pairs 500 --seed 10000
```

Pickups may be voluntary. Smart Runner remembers the cards picked up, but
never rules out beating cards merely because the opponent took an attack.
Browser, terminal, and protocol play all use this same policy.

## How a middlegame decision is made

1. **What is known.** Own hand, table, discards, cards the opponent visibly
   picked up (including our throw-ins), and the face-up trump, which is always
   the last card of the deck. Everything else is unknown.
2. **Sampling worlds.** The unknown cards are dealt randomly into the
   opponent's remaining hand and a deck order, with the trump at the bottom.
   Every sampled hand includes the opponent's known cards.
3. **Rollouts.** In every world, each legal candidate action is played and the
   game continues to the end in `durak/engine/simulator.py`, a bit-mask
   simulator using the controller's exact rules. Half the worlds use selective
   pickups for both players: save expensive trumps or accept a useful high
   card while more than four cards remain in the deck, provided the table and
   resulting hand stay small. The other half use cheapest-card defence.
   Attacks and throw-ins prefer cheap non-trumps. Throw-in candidates are the
   cheapest k eligible cards for each legal k.
   In a quarter of all worlds, an attack requiring a trump defence also checks
   the opponent's immediate choice to take, keeping the worse result for us.
   Before taking ourselves, remembered opponent cards are checked as possible
   next attacks, after either holding throw-ins or giving cheap eligible cards.
   Up to two known threats are considered. This checks every sampled world
   with six or fewer cards left in the deck, and one quarter earlier on.
   Each plan is scored across all samples; the opponent cannot choose a
   different best plan with advance knowledge of each sampled deck order.
   All candidates see the same worlds and continuation styles. This mixture
   is internal; there is one playing policy across all entry points.
4. **Exact leaves.** With at most `leaf_deck` (4) cards in the deck, rollouts
   stop when the sampled deck runs out. That world has perfect information, so
   the exact solver scores it, within a per-decision node budget.
5. **Racing.** All candidates share the same worlds. Worlds come in batches of
   64. After 128 worlds, a candidate is dropped when it trails the leader by
   more than 3 standard errors of the paired difference, so close decisions
   get up to 2048 worlds and clear ones finish early.
6. **Close choices.** Among surviving actions within one paired standard error
   of the leader, and no more than 0.03 behind in win-minus-loss score, prefer
   preserving useful cards. Cheap plain attacks shed cards; trump attacks cost
   more. A small pickup can preserve a high trump, but a large table or hand
   makes picking up expensive. This tie-break never overrides a larger score
   difference. The 0.03 cap equals 1.5 percentage points when draws count half.
7. **Losing late positions.** With at most six cards left, record each sampled
   position as the deck empties. If all surviving choices score a loss in
   every sample, compare those resulting hands: fewer cards, unanswerable
   threats, trump strength, matching ranks and initiative. This secondary
   `resistance` score replaces the ordinary conservation tie-break only in
   that all-losing case. It is a heuristic, not a winning probability, and
   cannot override a better win/draw/loss estimate or an exact decision.

Sampling is seeded from the position, so decisions are reproducible.

## Empty deck and diagnostics

Exact search now attempts positions of any size (the default `max_cards` is
36), bounded by `max_nodes` (500,000). A large position can be easy to solve;
an exhausted node budget falls back to rollout evaluation. An explicit lower
`max_cards` remains available as a resource limit. Exact win/draw/loss choices
are never overridden by the middlegame conservation rule.

The shared game log records `settings`, including `policy_revision: 3`, plus
`selection` (`score`, `conservation` or `resistance`), `score_leader`, each candidate's score,
sample count and conservation cost, and the number of immediate `reply_checks`.
`pickup_checks`, `pickup_threats` and `pickup_plan` identify the tested known
follow-up attacks and the opponent plan used to evaluate taking.
Each candidate's `continuation_score` records the ordinary rollout estimate
before reply checks, and `resistance` records its secondary late-game score.
`exact_search` distinguishes a solved position from a node or explicit card
limit. `exact_worlds` counts sampled worlds offered an exact leaf search;
individual leaf searches can still exhaust their budget and fall back.

## Results

Revision 3, at the default 2048-world budget, was checked on fresh paired deals:

| Opponent | Deal seeds | Games | Wins | Losses | Draws | Score |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Previous Smart Runner (revision 2 snapshot) | 80000–80029 | 60 | 32 | 26 | 2 | 55.0% |
| NextGen | 90000–90029 | 60 | 41 | 17 | 2 | 70.0% |

Each deal was played from both seats; draws count as half a win. The final
logic was fixed before these ranges were run. The comparison with revision 2
is close, so this does not establish an overall strength gain. It verifies the
specific pickup fixes while retaining competitive play in these small samples.
Median decision time was 106 ms against revision 2 and 90 ms against NextGen;
the slowest decision across these runs took 3.5 s (CPython 3.12, parallel games).

```sh
python3 -m durak.engine.matchup --engine smart_runner --opponent nextgen --pairs 30 --seed 90000
```

Historical revision 2 results: against Smart Runner at `0ee04a6` (with pickup
inference already removed), revision 2 won **39 games and lost 21**, a **65.0% score**.
Both engines used the default 2048-world budget. These were 30 paired deals
from the real controller, seeds 40000–40029, each played from both seats.
The implementation was fixed before these deals were run. An earlier
256-world pilot used different seeds, 30000–30011 (13 wins, 10 losses, 1 draw).

Across that full-strength comparison, revision 2's decisions took a
median of about **100 ms**, a 95th percentile of **602 ms**, and a maximum of
**2.8 s** on this machine (CPython 3.12, games run in parallel). These include
exact endgames. Large searches can still reach the node limit. The sample is
limited; this is evidence on these deals, not a guarantee against every style.

A separate revision 2 comparison against NextGen (seeds 50000–50029) finished
**36 wins, 20 losses, 4 draws**, a **63.3% score** with draws worth half a win.
Median decision time was 92 ms; the slowest decision took 4.3 s in that run.
The same deal range can be evaluated with the current engine using:

```sh
python3 -m durak.engine.matchup --engine smart_runner --opponent nextgen --pairs 30 --seed 50000
```

Replaying the earlier November 12 game positions, revision 2 took Q♣ instead
of beating it with Q♠, attacks with 7♦ instead of 7♠, and still chooses the
later J♠ attack. The 14-card position that previously received a winning
rollout score received an exact losing evaluation.

Revision 3 also covers the later game (`20261112-130821-786964-cbb04cbd.log`):
taking 8♥ is evaluated against the known 10♥ follow-up, including the option
of holding throw-ins, and the engine chooses K♥ instead. At the last two
pickups, all sampled outcomes lose, and it chooses 7♦ for both defences using
the practical resistance comparison. These positions are regression cases,
not a benchmark of overall strength.

## Limitations

- Continuations remain simplified. Attack checks cover a trump defence versus
  taking; pickup checks cover two throw-in policies and at most two publicly
  known follow-up cards. This is not a full adversarial search tree.
  The attack checks still compare outcomes inside individual sampled worlds,
  which can overestimate an opponent's ability to foresee the remaining deck.
- Throw-ins in the middlegame consider cheapest-first subsets only. The exact
  endgame considers all subsets.
- Python speed caps the number of worlds. Strength was still rising with more
  worlds, so a faster implementation (for example in Rust) should be stronger.

## Validation

`durak/engine/test_smart_runner.py` checks that simulator rollouts reproduce
`GameController` results from random positions for every legal first action,
including empty-deck finishes and draws, with greedy or selective pickups for
either seat. It also checks that remembered
opponent cards match the opponent's real hand in games against Dummy, that
taking keeps beating cards possible in sampled hands while preserving known
pickups, that racing drops only clearly worse candidates, and that complete
games against Dummy and NextGen stay legal. Additional regressions cover
immediate opponent pickups, conservative close choices versus clear tactical
advantages, and exact evaluation or explicit budget fallback at 14 live cards.
Pickup probes are checked against controller refills and open-trump ownership;
stopping and resuming rollouts at the empty deck must preserve their results.
Further tests cover consistent opponent plans across worlds and all-losing
tie-breaks without sacrificing a better outcome.
