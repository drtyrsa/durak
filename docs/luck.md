# Luck and engine strength

Finished browser games show **Luck balance**, from Unlucky through Typical to
Lucky, with starting-hand/draw and feature breakdowns. The bar uses a reference
percentile: **Very lucky — top 5%**, for example, means the estimated card luck
was among the best 5% in the reference, not a 95% chance of winning. It remains
in the sidebar when you close the result dialog. Winning with a percentile of
40 or below also shows **Won against the cards**.

## The display scale

The fixed `chance-v1-sr-dummy-202613000-100` reference contains 200 games of
default Smart Runner versus Dummy: seeds 202613000–202613099, each played with
the engine seats swapped and fresh engines. Both players' signed luck values
are included, giving 400 observations from **100 independent deals**. This
makes the display symmetric: zero luck is the 50th percentile, and reversing
players reverses the meter. No wins or losses enter the percentile calculation.

The sorted absolute game scores are bundled in `durak/web/static/app.js`
(rounded to nine decimal places). There is no online service or dependency on
local logs. To reproduce the reference, call `durak.engine.matchup.play_game`
with default `SmartRunnerEngine()` and `DummyEngine()` for each seed and each
seat, passing a `details={}` dictionary; collect
`abs(details['luck']['total'])`. Engine or model changes require a new reference
version, not silently replacing the data behind the existing one.

The percentile is `100 × (below + equal / 2 + 0.5) / 401`, where `below` and
`equal` count signed reference values. Ties receive their midpoint rank, and
the half-observation tail correction keeps finite-sample estimates away from
0% and 100%. Tails round up to whole percentages, so the most extreme values
say **top 1%** or **bottom 1%**, never "perfect luck." Percentiles at least 90
are **Very lucky**, at least 60 **Lucky**, at most 10 **Very unlucky**, and at
most 40 **Unlucky**; the middle is **Fairly even**.

For example, a raw score of +0.273759 maps to about the 95th percentile and
**Very lucky — top 5%**, instead of the old bar's 63.7% position. These are
approximate ranks within this reference; different playing styles can produce
different luck-score distributions. They are not universal population odds.
Unknown luck-model versions get no percentile until calibrated.

This transformation is **display only**. The controller, saved raw luck reports,
and matchup scores keep their existing values; a percentile is never substituted
into the score adjustment. Refreshing the browser also updates the display of
an already completed game without restarting the server.

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

The `chance-v1` model uses a fixed hand-value function, independent of all engine
evaluators. Each player's features are subtracted from the other's:

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

For each subsequent batch drawn, after resolving any pickup:

```
draw luck = actual value after drawing − expected value after drawing
total luck L = opening luck + sum(draw luck)
```

The expectation uses every equally likely subset of the remaining face-down
stock. It is calculated analytically using hypergeometric inclusion probabilities,
including pairs and the effect on both players' cheap answers. It does not sample
possible games or read future stock order. Receiving the entire remaining stock
is deterministic at that point and contributes zero. The face-up bottom trump
is excluded from the random pool, so manoeuvring to receive it earns no extra
luck credit. Its suit still defines trump values throughout the game.

Playing, retaining, attacking with, or picking up a card adds no luck by itself.
Those decisions determine the position against which the next draw is compared.
Holding 8♥ when facing 7♥ is a favourable fit when the cards arrive; choosing to
save that 8♥ or attack into it is not another random event. The same answer is
not counted anew on each attack. Suit coverage and pairs are only rough proxies:
several attacks may compete for one defender, and initiative and endgame tactics
are not represented. This is an estimate of card luck, not a perfect separation
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
