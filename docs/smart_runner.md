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
   Every sampled hand includes the opponent's known cards. Near the end,
   enumerate all hidden arrangements when both continuation styles fit the
   128-trial limit. With `u` unknown non-bottom cards and `h` empty opponent
   slots, there are `choose(u, h) × (u − h)!` arrangements: the order of the
   opponent's hand does not matter, but the stock order does. Every enumerated
   arrangement receives equal weight and both styles. Its greedy trial blends
   the ordinary and pickup-checked scores equally, preserving the check's
   overall one-quarter weight.
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
4. **Exact leaves.** With at most `leaf_deck` (12) cards in the deck, rollouts
   stop when the sampled deck runs out. That world has perfect information, so
   the exact solver scores it. One defended round can refill both hands by
   twelve cards; an eight-card stock can disappear after four attacks without
   ever visiting the old four-card threshold. Up to 128 shared worlds are
   sampled, with 20,000 nodes per exact leaf and a 500,000-node decision budget.
   Collect all rollout leaves first, deduplicate identical positions and share
   one exact solver across them. Every unique leaf first gets a share of the
   budget; unresolved leaves can then receive more, up to the per-leaf cap.
   Completed subtrees survive interrupted searches. The solver's cache has a
   separate capacity, so a short search does not evict results simply because
   its node allowance is small. The decision budget is now a strict ceiling.
   Every use of a leaf shares its value: a later proof also updates earlier
   rollout scores and reply-plan comparisons. Cache lookups still work after
   the search budget runs out. Up to 8192 proven leaf values persist between
   decisions, with attacker/defender roles normalized; a new game clears them.
   Unproven leaves retain their ordinary continuation score and never enter
   the exact-value cache.
5. **Racing.** All candidates share the same worlds. Worlds come in batches of
   64. After 128 worlds, a candidate is dropped when it trails the leader by
   more than 3 standard errors of the paired difference, so close decisions
   get up to 2048 worlds and clear ones finish early. This applies to earlier
   middlegame decisions. Late decisions evaluate their bounded batch before
   selecting a move, so provisional rollout values cannot eliminate a move
   before its shared exact results arrive.
6. **Close choices.** Among surviving actions within one paired standard error
   of the leader, and no more than 0.03 behind in win-minus-loss score, prefer
   preserving useful cards. Cheap plain attacks shed cards; trump attacks cost
   more. A small pickup can preserve a high trump, but a large table or hand
   makes picking up expensive. This tie-break never overrides a larger score
   difference. The 0.03 cap equals 1.5 percentage points when draws count half.
   Fully enumerated hidden sets have no sampling error; conservation then
   breaks exact score ties only. Continuation-model errors and unresolved
   endgame leaves still remain possible.
7. **Losing late positions.** With at most six cards left, record each sampled
   position as the deck empties. If all surviving choices score a loss in
   every sample, compare those resulting hands: fewer cards, unanswerable
   threats, trump strength, matching ranks and initiative. This secondary
   `resistance` score replaces the ordinary conservation tie-break only in
   that all-losing case. It is a heuristic, not a winning probability, and
   cannot override a better win/draw/loss estimate or an exact decision.
8. **Last-trump reserve.** With 6–12 cards left, consider taking a non-trump
   attack when the only beating card is our last trump. This applies only if
   the pickup adds ordinary-suit answers to live unseen or remembered cards
   that our current non-trumps cannot beat. The table must contain at most
   three cards, the resulting hand at most eight, and the hand plus a
   conservative expected throw-in allowance at most nine. Known eligible
   throw-ins count in full; unseen ones use their chance of being in the
   opponent's hand. It does not assume that the opponent lacks beating cards.
   Both actions receive the full shared sample. Taking may override a score
   gap of 0.1 for one new answer, or 0.2 for two or more, in win-minus-loss
   units (5 or 10 percentage points of game score). These are fixed heuristic
   limits, not measured winning probabilities. A candidate scoring a win in
   every trial is protected, as are all decisions made by the exact solver.
   Earlier pickups risk blocking useful refills; with fewer than six cards
   left, accepting extra cards can be especially costly. This preference
   therefore applies only in the specified stock window.

Sampling is seeded from the position. Replaying the full game reproduces
decisions; an isolated decision can differ if it lacks exact proofs cached
earlier in that game.

## Empty deck and diagnostics

Exact search now attempts positions of any size (the default `max_cards` is
36), bounded by `max_nodes` (500,000). A large position can be easy to solve;
an exhausted node budget falls back to rollout evaluation. An explicit lower
`max_cards` remains available as a resource limit. Exact win/draw/loss choices
are never overridden by the middlegame conservation rule.

The shared game log records `settings`, including `policy_revision: 6`, plus
`selection` (`score`, `conservation`, `resistance` or `reserve`), `score_leader`, each candidate's score,
sample count and conservation cost, and the number of immediate `reply_checks`.
`pickup_checks`, `pickup_threats` and `pickup_plan` identify the tested known
follow-up attacks and the opponent plan used to evaluate taking.
Each candidate's `continuation_score` records the ordinary rollout estimate
before reply checks, and `resistance` records its secondary late-game score.
`exact_search` distinguishes a solved position from a node or explicit card
limit. `sampling` distinguishes sampled from fully enumerated hidden sets;
`hidden_worlds` records the number of possible arrangements. `worlds` counts
trials (including both continuation styles), not distinct arrangements.
`exact_worlds` counts trials with at least one leaf searched or already proven;
it does not imply every candidate in that trial was solved exactly.
`leaf_evaluations` counts leaf uses, including reply probes;
`leaf_unique_positions` counts distinct leaves. `leaf_searches`, `leaf_solved`
and `leaf_search_limits` count attempts, completed root searches and interrupted
searches. `leaf_nodes_used` includes work in failed attempts. `leaf_cache_hits`
counts persistent-value and solver-root hits, excluding internal recursive
cache hits. `leaf_exact_evaluations` and `leaf_fallbacks` report how many leaf
uses ultimately have proven or approximate values. Search settings remain
resource controls; there is one default playing policy.

When the last-trump rule is eligible, `reserve_pickup` records the trump,
`new_plain_covers`, `hand_after_take`, `throw_in_allowance`, `score_gap`,
`score_gap_limit` and whether the preference was `used`. Candidate scores
remain the unmodified simulation estimates, so the log exposes the tradeoff.

## Results

Revision 6 adds the last-trump reserve preference without increasing search
budgets. In the audited seed **202620078**, action 20 previously used the last
trump, K♥, against K♣ with twelve cards in stock. Taking collects 7♦, K♦ and
K♣, preserves K♥, and supplies ordinary answers to the still-live 9♦ and Q♦.
The hand grows to eight; the throw-in allowance is 0.8 cards. The raw
simulation still prefers defending (−0.21875 versus −0.40625), but the 0.1875
gap falls within the rule's 0.2 limit. The log explicitly records this override.
A full replay now wins against Dummy from both seats; action 20 is the first
changed move in the original losing seat. This is a regression example, not
independent strength evidence or a proof that taking is optimal.

An initial prototype also protected the last trump earlier in the game.
Pilots exposed losses after pickups with 20 and 24 cards still in stock:
saving a trump can delay useful refills. The final 6–12-card window and
throw-in allowance were fixed before the validation matches. The engine
still has one playing policy, and neither rollout outcomes nor exact-solver
values are relabeled as proven by this heuristic.

Validation against Dummy reused the recorded revision 5 baseline on
**202618000–202618099**, playing revision 6 from both seats on all 100 deals.
Both versions finished with **162 wins, 32 losses and 6 draws** (82.50% raw
score). Only two games changed moves, and both remained wins. The chance-v2
adjusted scores were 81.31% for revision 5 and 81.28% for revision 6. This
establishes no overall strength gain: the new preference fixes the audited
decision and rarely intervenes elsewhere in this sample.

Fresh direct play against revision 5 used **202622000–202622029**, both seats:
**29 wins, 29 losses and two draws**. The reserve preference did not override
any decision in these games, so the tie provides little evidence about its
strength. The observed zero spread between paired scores is not proof of
equivalence on other deals.

Across the 200 Dummy games and 60 direct games, all **7617** revision 6
decisions respected the existing leaf-search budget. Frozen engine sources,
complete game logs, per-deal comparisons and the audit summary are saved in
`logs/benchmarks/smart-runner-v6-development-20261113/`. The shared simulator
and empty-deck solver are unchanged.

Revision 5 keeps revision 4's search budgets and continuation policies while
sharing exact proofs and enumerating small hidden sets. In the audited
seed **202617093**, action 34 has only 42 hidden arrangements. The previous
version sampled 128 trials and chose J♥ to beat 6♠. Revision 5 evaluates all
42 arrangements with both styles (84 trials), finds only 22 distinct leaves,
and chooses **8♠** using **149,427 nodes**. Of 504 leaf uses, 370 are proven
and 134 remain approximate. This agrees with the earlier 18.9-million-node
probe's choice, without claiming an exact solution to the hidden-information
game. A full replay from the same initial shuffle now wins against Dummy in
both seats. In the original losing seat, action 34 is the first changed move.
These are regression examples, not independent strength evidence.

The earlier repeated pickups and the later K♥ attack remain separate
continuation-policy weaknesses. This change does not add a general search
over repeated pickup plans or exact play while stock remains.

A fresh comparison used **202618000–202618099**, both seats, with frozen
revision 4 and 5 snapshots. Each version played 200 games against Dummy:

| Version | Wins | Losses | Draws | Raw score | chance-v2 adjusted score |
| --- | ---: | ---: | ---: | ---: | ---: |
| Revision 4 | 165 | 26 | 9 | 84.75% | 83.99% |
| Revision 5 | 162 | 32 | 6 | 82.50% | 81.31% |

The paired raw difference is **−2.25 percentage points**, with an approximate
95% interval of **−7.76 to +3.26 points** over 100 independent deals. The
observed score is lower; this sample establishes neither a strength gain nor
a clear regression. Better reuse of exact results fixes the audited decision,
but simplified continuations and partial proofs still affect playing strength.

Direct play against revision 4 used **202619000–202619029**, both seats:
revision 5 won **32**, lost **27** and drew **1**, a **54.17% raw score** and
53.51% luck-adjusted score. The raw 95% interval over the 30 paired deals is
**45.65–62.69%**. This is encouraging against the previous engine but, like
the Dummy comparison, does not establish an overall strength gain.

Across revision 5's 1756 late decisions against Dummy, 565,897 of 878,405 leaf
uses had proven values (64.4%); the rest remained approximate. All logged
searches respected the strict node budget. Median middlegame time was
769 ms versus 893 ms for revision 4; the 95th percentile was 3.81 s versus
4.53 s. These are measurements during concurrent games, with varying load,
not isolated latency benchmarks. Full logs, frozen sources, seeds, summaries
and diagnostic audits are in
`logs/benchmarks/smart-runner-v5-development-20261113/`.

Revision 4 changes the transition to the endgame, leaving the earlier rollout
policy and the empty-deck solver intact. The three previously audited low-luck
Dummy wins (seeds 202614037, 202614065 and 202614082) now finish as Smart Runner
wins when replayed from the same initial shuffles. All three also win from the
opposite seat. These are regression examples, not an independent strength test.

At the specific eight-card-stock position in seed 202614065, it chooses 7♦
instead of K♥, with exact endgame leaf searches enabled. The old king attack
was evaluated only with simplified continuations. This does not claim that
7♦ wins against every possible hidden hand and stock order.

An independent comparison used seeds **202615000–202615099**, both seats,
fresh engines, and frozen policies. Each version played 200 games against Dummy:

| Version | Wins | Losses | Draws | Raw score | chance-v2 adjusted score |
| --- | ---: | ---: | ---: | ---: | ---: |
| Revision 3 | 169 | 24 | 7 | 86.25% | 86.85% |
| Revision 4 | 167 | 26 | 7 | 85.25% | 87.09% |

The paired raw difference is **−1.0 percentage point**, with an approximate
95% interval of **−6.6 to +4.6 points** over 100 independent deals. This fixes
the identified lookahead weakness but does **not establish an overall strength
gain**. The adjustment also does not establish a ranking. All raw and adjusted
scores describe performance against Dummy, not a universal engine rating.

A separate head-to-head check, seeds **202616000–202616019**, finished with
**21 wins, 18 losses and one draw** for revision 4: a 53.75% raw score and
51.34% luck-adjusted score. With only 20 paired deals, the raw 95% interval
is approximately 36.7–70.8%, so this also does not establish a strength gain.
Its full logs are in the sibling `head-to-head/` benchmark directory.

The cost is measurable: median middlegame decision time was 391 ms versus
179 ms for revision 3; the 95th percentile was 1.97 s versus 0.55 s, and maxima
were 3.34 s versus 1.03 s. These timings include concurrent games and vary by
machine. Results and full decision logs are saved locally under
`logs/benchmarks/luck-v2-development-20261113/validation/`.

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
tie-breaks without sacrificing a better outcome, plus the eight-card-stock
transition that used to bypass exact leaf search entirely.

Revision 5 adds exhaustive hidden-world coverage and continuation-weight
checks, shared-proof updates to earlier predictions and reply choices,
attacker/defender normalization, cached draws with no remaining budget, new
game resets, and strict total/per-leaf limits without caching approximations.
The 42-arrangement decision is a regression fixture. Shared-solver tests
check independent cache capacity and work budgets, including bounded eviction
and read-only outcome lookups after interrupted searches. Validation passed
330 headless Python tests (plus 54 subtests) and 9 JavaScript checks; no GUI
code changed in revision 5.
