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

## How a middlegame decision is made

1. **What is known.** Own hand, table, discards, cards the opponent visibly
   picked up (including our throw-ins), and the face-up trump, which is always
   the last card of the deck. Everything else is unknown.
2. **What the opponent's takes reveal** (`infer_takes`, on by default). Each
   unknown opponent card is a *slot* with a set of cards it cannot be. When the
   opponent takes an attack, every current slot forbids the cards that would
   have beaten it. New draws start unconstrained. When an unknown card leaves
   the opponent's hand, the most constrained compatible slot is removed. Slots
   held through more takes forbid supersets, so this rule never produces a
   wrong constraint. If a known card could have beaten the attack, the take
   was voluntary and teaches nothing; contradictions reset the constraints.
3. **Sampling worlds.** The unknown cards are dealt randomly into the
   opponent's slots (most constrained first) and a deck order, with the trump
   at the bottom. A world that cannot satisfy the constraints is sampled
   without them.
4. **Rollouts.** In every world, each legal candidate action is played and the
   game continues to the end in `durak/engine/simulator.py`, a bit-mask
   simulator using the controller's exact rules. Both sides follow a cheap
   policy: cheapest matching card, keep trumps while the deck lasts, always
   beat. Throw-in candidates are the cheapest k eligible cards for each legal k.
5. **Exact leaves.** With at most `leaf_deck` (4) cards in the deck, rollouts
   stop when the sampled deck runs out. That world has perfect information, so
   the exact solver scores it, within a per-decision node budget.
6. **Racing.** All candidates share the same worlds. Worlds come in batches of
   64. After 128 worlds, a candidate is dropped when it trails the leader by
   more than 3 standard errors of the paired difference, so close decisions
   get up to 2048 worlds and clear ones finish early.

Sampling is seeded from the position, so decisions are reproducible.

## Results

Paired deals from the real controller, each deal played from both seats,
seeds 10000+, separate from the tuning seeds 0–1999:

| Opponent | Games | Wins | Losses | Draws | Score |
| --- | ---: | ---: | ---: | ---: | ---: |
| NextGen | 2,000 | 1,319 | 617 | 64 | 67.6% |
| Dummy | 1,000 | 845 | 110 | 45 | 86.8% |

Middlegame decisions took a median of about 130 ms on this machine (CPython
3.10), with a maximum of about 0.65 s in a 30-game sample. The number of
sampled worlds was the main lever during tuning (seeds 0–999 against NextGen):

| Setting | Score |
| --- | ---: |
| 48 worlds | 51.0% |
| 512 worlds | 63.2% |
| + exact leaves | 66.0% |
| + take inference | 66.1% (+1.6 on seeds 1000–1999) |
| + racing, up to 2048 worlds | 67.7% |

Smarter rollout policies (saving high cards or trumps, voluntary takes) all
scored worse. Rollouts seem to work best when they resemble how real
opponents play.

## Limitations

- Take inference assumes the opponent takes only when it cannot beat. That is
  true of Dummy and NextGen; humans who take voluntarily while holding a
  beater can mislead it until a contradiction resets the constraints.
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
opponent cards and take constraints always match the opponent's real hand in
games against Dummy, that racing drops only clearly worse candidates, and that
complete games against Dummy and NextGen stay legal.
