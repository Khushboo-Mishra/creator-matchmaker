# Creator Matchmaker

Build the creator mix that fits a campaign.

Most tools rank creators one at a time. This one casts a roster: it picks the mix,
gives each member a role, and says who to activate first.

A campaign goes in. Every candidate channel is scored across six dimensions and the
numbers are stored. Weights are then adjusted to say what matters for this campaign,
and the ranking reorders instantly because nothing is recomputed. Once creators are
picked, each is assigned a role and a creative direction built on what they already
do well.

## The one architectural decision

Score each channel once, on every dimension, and store the numbers. Weight sliders
do arithmetic on values that already exist. No API call runs when a weight changes.
Everything else in this repo follows from that.

## The six dimensions

| Dimension | Measures | Source |
|---|---|---|
| `audience_relevance` | Does this audience care about the category | Model, reading sampled comments |
| `engagement` | Is the audience alive | Arithmetic, `(likes + comments) / views` |
| `brand_fit` | Can the brand sit beside this content | Model, reading titles against the rules file |
| `momentum` | Growing or fading | Arithmetic, median views last 5 vs previous 10 |
| `speed_to_activate` | How fast they can turn a video around | Arithmetic, uploads in the last 90 days |
| `trend_fit` | Do they already cover what is rising | Model, with search grounding |

Three of six are plain arithmetic on data the API returns directly. That is deliberate.
When someone asks where a number came from, half the answers are a formula.

## Layout

```
config/rules.md              campaign rules. Five fixed headings, read by the scorer
data/handles.txt             one YouTube handle per line
data/channels/<handle>.json  pulled channel data        (gitignored, regenerate)
data/scores/<handle>.json    six scores plus reasons    (gitignored, regenerate)
schemas/                     the JSON contracts both of the above must satisfy
src/pull.py                  YouTube Data API -> data/channels/
src/arithmetic.py            the three scores that need no model
src/score_ai.py              the three that do
src/build_scores.py          merges both into data/scores/
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in the two keys
```

`YOUTUBE_API_KEY`: create a project in the Cloud Console, enable YouTube Data API v3,
generate an API key. Free.

`GEMINI_API_KEY`: from aistudio.google.com. Free tier is enough to develop against.

## Run

```bash
python -m src.pull                      # pull every handle in data/handles.txt
python -m src.pull @somebody            # or just one
python -m src.build_scores --no-model   # arithmetic only, no Gemini key needed
python -m src.build_scores              # all six dimensions
```

## Working agreements

**The schemas are contracts.** `schemas/channel.schema.json` and
`schemas/scores.schema.json` define the files that move between people. Do not rename
a field without saying so. Anyone can work against a stub that satisfies the schema,
which means nobody waits for anyone else's part to be finished.

**Data is never committed.** Pulled channels and generated scores are gitignored.
They are reproducible, they go stale, and they make diffs unreadable. Commit one
small sample only if the team needs a shared fixture.

**Quota discipline.** `search.list` has its own small daily bucket and this repo does
not use it. Channels are resolved by handle at 1 unit each. Never re-pull live during
a demo, read the cached JSON.

**Medians, not means.** One viral video should not rescue a dead channel.

**Fixed anchors, not pool-relative normalisation.** Normalising across the candidate
set means adding one channel silently changes everyone else's score.

## Known limits

- **No audience demographics.** Age, gender and location are only available to a
  channel's own owner. `audience_relevance` is inferred from comment content, which
  is a proxy, not a measurement.
- **Roles come from title patterns**, not from watching every video. A reasonable
  proxy, not ground truth.
- **Trend fit decays.** A ranking is accurate on the day it runs.
- **Scores are not comparable across campaigns**, because the weights and the rules
  file change.
- **No accuracy claim.** There is no ground truth on which past creator selections
  succeeded. The claim is faster and reproducible, with a written reason attached to
  every choice. Not better picks.
