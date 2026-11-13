# Luck and engine strength

Finished browser games show **Luck balance**, from Unlucky through Typical to
Lucky, with starting-hand/draw and feature breakdowns. The bar uses a reference
percentile: **Very lucky — top 5%**, for example, means the estimated card luck
was among the best 5% in the reference, not a 95% chance of winning. It remains
in the sidebar when you close the result dialog. Winning with a percentile of
40 or below also shows **Won against the cards**.

## The display scale

New games use the fixed `chance-v2-sr3-dummy-202614000-100` reference: 200 games
of Smart Runner revision 3 versus Dummy, seeds 202614000–202614099, each played
with the engine seats swapped and fresh engines. The saved actions were replayed
with the new luck model; game outcomes do not enter calibration. Both players' signed luck values
are included, giving 400 observations from **100 independent deals**. This
makes the display symmetric: zero luck is the 50th percentile, and reversing
players reverses the meter. No wins or losses enter the percentile calculation.

The sorted absolute game scores are bundled in `durak/web/static/app.js`
(rounded to nine decimal places). There is no online service or dependency on
local logs. To reproduce the reference, call `durak.engine.matchup.play_game`
with `SmartRunnerEngine(leaf_deck=4, leaf_nodes=5000, leaf_budget=150000)`
(the revision 3 policy) and `DummyEngine()` for each seed and each seat,
passing a `details={}` dictionary; collect
`abs(details['luck']['total'])`. Engine or model changes require a new reference
version, not silently replacing the data behind the existing one.

The percentile is `100 × (below + equal / 2 + 0.5) / 401`, where `below` and
`equal` count signed reference values. Ties receive their midpoint rank, and
the half-observation tail correction keeps finite-sample estimates away from
0% and 100%. Tails round up to whole percentages, so the most extreme values
say **top 1%** or **bottom 1%**, never "perfect luck." Percentiles at least 90
are **Very lucky**, at least 60 **Lucky**, at most 10 **Very unlucky**, and at
most 40 **Unlucky**; the middle is **Fairly even**.

The original `chance-v1-sr-dummy-202613000-100` reference remains bundled for
old reports. For example, a **v1** score of +0.273759 still maps to about the
95th percentile and **Very lucky — top 5%**. These are
approximate ranks within this reference; different playing styles can produce
different luck-score distributions. They are not universal population odds.
Unknown luck-model versions get no percentile until calibrated.

The percentile transformation is **display only**; it is never substituted into
the matchup score adjustment. Version 2 changes the underlying raw estimator,
so restart the Python server to use it for new games. Existing saved reports
retain their original model and scale.

## Where the estimate is available

The shared controller measures every engine identically, including external
engines and games without a GUI. It never supplies the estimate to either
engine or the browser during play: calculating it uses both hands and the
remaining stock. Completed logs save it under `luck`, with a model version,
player-1 perspective, opening/refill totals and per-feature contributions.
Older logs remain readable and have no estimate.

```sh
python3 -m durak.gamelogger logs/your-game.log --luck
python3 -m durak.engine.matchup --engine nextgen --opponent smart_runner --pairs 100 --seed 200000
durak-autoplay durak-nextgen durak-smart-runner --matches-number=1 --match-size=100
```

## What counts as luck

The `chance-v2` model retains the original hand-value function for opening hands
and draws that leave cards in the deck. It is independent of engine policies.
Each player's features are subtracted from the other's:

| Feature | Definition | Weight in game-score units |
| --- | --- | ---: |
| Trumps | Number of trumps | 0.060 |
| High cards | Sum of ranks, six = 0 through ace = 1 | 0.030 |
| Cheap answers | Opposing cards with a same-suit beater one or two ranks higher | 0.020 |
| Pairs and sets | Unordered same-rank pairs; triple = 3, four = 6 | 0.008 |
| Suit coverage | Nontrump suits containing at least a seven | 0.015 |

These weights are initial hypotheses, **not fitted win probabilities**. They
should be refined on separate training games, versioned, and then evaluated on
fresh seeds. Do not tune them on the results you want to rank engines by.

For the opening deal, expected advantage is exactly zero: exchanging the two
six-card hands reverses the value, and both allocations are equally likely.
Opening luck is therefore the observed difference in their feature values.

For each subsequent random draw, after resolving any pickup:

```
draw luck = actual value after drawing − expected value after drawing
total luck L = opening luck + sum(draw luck)
```

The expectation uses every equally likely subset of the remaining face-down
stock. For earlier draws it is calculated analytically using hypergeometric inclusion probabilities,
including pairs and the effect on both players' cheap answers. It does not sample
possible games or read future stock order. Receiving the entire remaining stock
is deterministic at that point and contributes zero. The face-up bottom trump
is excluded from the random pool, so manoeuvring to receive it earns no extra
luck credit. Its suit still defines trump values throughout the game.

### The draw that empties the deck

When both players draw from the final stock, evaluate the **whole allocation**
instead of adding separate card-feature bonuses. Keep their existing hands,
draw quotas, next attacker and visible trump recipient fixed. Enumerate every
split of the hidden cards between those two hands (at most 462 allocations).
Each resulting endgame is valued at +½ for a player-1 forced win, 0 for a draw,
and −½ for a forced loss. Subtract the mean value of all possible splits from
the value of the actual split. This replaces, rather than adds to, the old
feature correction for these cards.

Exact search has a 100,000-node per-position limit and a 500,000-node total
limit per final refill. If either budget runs out, use a fixed greedy endgame
continuation for that allocation. All allocations are still evaluated, in a
canonical order independent of the actual draw; the observed split receives
no special budget. The baseline and observation therefore use the same value
function, and the correction remains zero-mean even with fallbacks. These
values describe endgame strength, not a win probability against a particular
opponent. An exact allocation is solved against optimal play, not against Dummy.

If one player receives the whole stock, or all hidden cards go to one player
and only the visible trump to the other, the allocation is deterministic:
zero luck, no search. Initiative and the decision to fight for the exposed
trump are held fixed; they are not awarded random luck credit.

The report adds an `endgame` component and `endgame_draws` diagnostics: stock
size, next attacker, allocations, exact/fallback counts, nodes, actual value,
expected value and correction. The browser shows **Endgame draws** in the
breakdown. This is shared controller logic for every engine and UI; hidden
information stays out of engine inputs and live browser snapshots.

In the audited seed 202614065, Smart Runner's last eight cards of stock had
35 possible allocations. All were solved exactly. Its actual allocation was
a forced loss (value −0.5), against an expected value of −1/7. The correction
is −5/14, giving Dummy total luck **+0.29687**, rather than the old **−0.05613**.
Dummy benefited from the final suit fit despite receiving worse cards earlier.

Playing, retaining, attacking with, or picking up a card adds no luck by itself.
Those decisions determine the position against which the next draw is compared.
Holding 8♥ when facing 7♥ is a favourable fit when the cards arrive; choosing to
save that 8♥ or attack into it is not another random event. The same answer is
not counted anew on each attack. Earlier hand features remain rough proxies:
several attacks may compete for one defender, and they do not value initiative
or tactics. The last split does, but a decisive earlier draw can still be
misvalued, particularly when the final allocation is deterministic. Bounded
endgame evaluations may also fall back to imperfect play. This is an estimate
of card luck, not a perfect separation
of every source of luck and skill in an individual game.

## Comparing engines

The ordinary record and score remain unchanged. Each result `R` is 1 for a win,
½ for a draw, 0 for a loss. The additional estimate is:

```
adjusted score = mean(R − L)
Elo-style difference = 400 × log10(score / (1 − score))
```

For example, a win with `L = +0.15` contributes 0.85, while a win with `L = −0.15`
contributes 1.15. Losses and draws are adjusted too. Individual adjusted results
and even small-sample averages can fall outside [0, 1]; **they are not clipped**,
because that would bias the estimate. Elo differences are null outside (0, 1).
The conversion describes performance against this opponent, not a persistent
universal rating. Elo by itself does not remove card luck.

This is a chance-only control variate, following the principle behind
[MIVAT](https://ijcai.org/proceedings/2009/326), also described in the
[AIVAT paper](https://poker.cs.ualberta.ca/publications/aaai18-burch-aivat.pdf).
Under a uniform shuffle, each correction has expectation zero, even with an
imperfect fixed heuristic. Consequently the adjusted score estimates the same
expected game result as the ordinary score. A useful heuristic can reduce its
variance; a poor one can increase it. This implementation does not do AIVAT's
additional player-strategy corrections.

Matchup JSON includes `strength.raw`, `strength.luck_adjusted`, `mean_luck`, and
`variance_ratio` (adjusted/raw variance; below 1 means less observed noise).
Both estimates include a standard error and approximate 95% Student-t interval.
For paired matches, each shuffled deal's two seat-swapped results are averaged
first; the independent sample count is **pairs**, not games. Opening luck cancels
exactly within a pair; the remaining adjustment addresses refill differences
caused by the different paths the two games take. Autoplay uses independent
shuffles, so its unit is one game, regardless of its grouping into matches.

Small samples deserve caution. Intervals are approximate, can extend beyond
[0, 1], and are null with fewer than two independent deals or no observed score
variation. Null is not certainty. Elo interval endpoints outside (0, 1) are also
null. Compare both intervals and the variance ratio before treating the adjusted
ranking as stronger evidence; use many independent deals and fresh seeds.

An initial validation of these fixed weights used 1,000 independent Dummy
self-play games (seeds 202611120–202612119): the observed variance ratio was
0.895, a roughly 10% reduction. NextGen versus Dummy on 40 paired deals
(202611120–202611159) gave 0.917, roughly 8% less variance; the raw score was
81.25% and adjusted score 82.93%. These are checks of the first model, not a
guarantee that it reduces noise for every matchup. Neither sample was used to
fit the weights.

For version 2, both formulas were recorded on **identical actions** in fresh
Smart Runner–Dummy games, seeds 202615000–202615099, each from both seats:

| Smart Runner policy | Raw score | v1 adjusted | v2 adjusted | v1 variance ratio | v2 variance ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| Revision 3 | 86.25% | 86.41% | 86.85% | 0.872 | 0.870 |
| Revision 4 | 85.25% | 85.88% | 87.09% | 0.891 | 0.923 |

Thus v2 reduced observed variance versus the raw score by about 13% and 8%,
respectively. It did **not** consistently beat v1 at variance reduction, even
though it corrects the audited final-draw misclassification. The revised
engine's v2 adjusted interval was approximately 82.49–91.69%; the previous
engine's was 82.33–91.38%. These overlapping intervals do not establish a
strength difference. The policies, weights and search limits were fixed before
this validation; calibration used a different seed range and no outcomes.

Three of revision 4's 26 losses to Dummy still had negative estimated Dummy
luck. The lowest was seed 202615059, seat 0: −0.10941. Its last four cards all
went to Smart Runner, a deterministic refill that contributes zero luck; Dummy
then led its sole remaining 9♠ and won. Earlier luck estimates and middlegame
choices still matter. A negative meter does not prove that an upset is
impossible or that the engine's previous choices were optimal.
