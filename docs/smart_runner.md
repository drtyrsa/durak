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
   simulator using the controller's exact rules. Both sides follow a cheap
   policy: cheapest matching card, keep trumps while the deck lasts, always
   beat. Throw-in candidates are the cheapest k eligible cards for each legal k.
4. **Exact leaves.** With at most `leaf_deck` (4) cards in the deck, rollouts
   stop when the sampled deck runs out. That world has perfect information, so
   the exact solver scores it, within a per-decision node budget.
5. **Racing.** All candidates share the same worlds. Worlds come in batches of
   64. After 128 worlds, a candidate is dropped when it trails the leader by
   more than 3 standard errors of the paired difference, so close decisions
   get up to 2048 worlds and clear ones finish early.

Sampling is seeded from the position, so decisions are reproducible.

## Results

The current policy scored 39 wins, 19 losses, and 2 draws against NextGen in
30 paired deals from the real controller (seeds 20000–20029, each deal played
from both seats). That is a 66.7% score, counting a draw as half a win. This is
a small sample, separate from the original tuning seeds 0–1999.

Middlegame decisions took a median of about 83 ms on this machine (CPython
3.12). To repeat the comparison:

```sh
python3 -m durak.engine.matchup --engine smart_runner --opponent nextgen --pairs 30 --seed 20000
```

Smarter rollout policies (saving high cards or trumps, voluntary takes) all
scored worse. Rollouts seem to work best when they resemble how real
opponents play.

## Limitations

- Rollouts model both players with one simple policy. This is flat Monte
  Carlo: it does not model the opponent reacting to our choices.
- Throw-ins in the middlegame consider cheapest-first subsets only. The exact
  endgame considers all subsets.
- Python speed caps the number of worlds. Strength was still rising with more
  worlds, so a faster implementation (for example in Rust) should be stronger.

## Validation

`durak/engine/test_smart_runner.py` checks that simulator rollouts reproduce
`GameController` results from random positions for every legal first action,
including empty-deck finishes and draws. It also checks that remembered
opponent cards match the opponent's real hand in games against Dummy, that
taking keeps beating cards possible in sampled hands while preserving known
pickups, that racing drops only clearly worse candidates, and that complete
games against Dummy and NextGen stay legal.
