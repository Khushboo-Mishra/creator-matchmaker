# Creator Matchmaker

Campaign input -> YouTube discovery -> measurable screening -> evidence evaluation ->
relative six-dimension ranking -> four-creator roster -> marketer report and internal audit.

The backend entrypoint is `python -m src.matchmaker`. The older
`src.pull` / `src.build_scores` scripts remain available for compatibility, but
they are **not the locked campaign pipeline**.

## Install and run a complete demo

From this repository folder with your virtual environment active:

```powershell
python -m pip install -r requirements.txt
python -m src.matchmaker run --campaign examples/campaign.json --mode demo
```

This runs the entire backend with **clearly labeled synthetic creators and model
responses**. It requires no API keys. Expected result: 26 discovered, 25 measurable,
20 shortlisted, and 4 recommended creators. Change the campaign JSON to try another
objective or audience; synthetic judgments remain test fixtures, not real matching.

The command prints the saved run folder under `data/runs/<run-id>/`:

- `report.pdf`: plain-language marketer brief with roster, evidence, comparisons,
  alternatives, warnings, and method limitations.
- `report.md`: the same report in text form.
- `audit.json`: complete campaign, data, scores, evidence, counts, screening
  decisions, settings, similarity components, selection terms and versions.

Use `--no-pdf` if you only need JSON/Markdown and have not installed ReportLab.
Generated runs and secrets are gitignored.

## Run with live services

Copy `.env.example` to `.env` and configure YouTube and Gemini keys, then:

```powershell
python -m src.matchmaker run --campaign examples/campaign.json --mode live
```

Live mode calls the existing YouTube discovery/data endpoints and Gemini
generation/embedding adapters. Network/API failures stop the run; they never
silently substitute synthetic scores. Live access, model availability, permissions
and quota must be validated in your own configured environment. The repository
tests mock external services and do not establish live service success.

Campaign fields: product description, objective, specific goal, audience, and
banned phrases/raw tone/category exclusions/competitors. No mandatory trend or
message field. Supported objectives: awareness, consideration, conversion, launch,
trend response. Objective presets are transparent starting values, not calibrated
claims of optimal campaign performance.

## Google Trends verification

Google Search grounding is not Google Trends confirmation. The new pipeline
accepts official Google Trends interest-over-time CSV exports through an explicit
import boundary; automatic Google Trends retrieval is **not implemented**.

1. Propose topics using Gemini:
   `python -m src.trends propose --campaign examples/campaign.json --output proposals.json`
2. Download one English Google Trends CSV per proposed topic from Google Trends.
3. Create a manifest with `campaign_fingerprint` copied from proposals and
   `exports` entries containing `topic`, `file` (relative to manifest),
   `source_url` (trends.google.com), `geo`, and `window`.
4. Import: `python -m src.trends import --manifest exports.json --output trends.json`
5. Run with `--trends trends.json`.

The importer records original-series data and export hashes, compares recent-half
and previous-half mean interest, and retains rising topics. Operator-supplied CSV
origin is recorded, not cryptographically certified. Snapshot dates, geography and
time windows remain visible. No snapshot -> null Trend Fit; a valid snapshot with
no matching rising topics -> low/zero Trend Fit. No trend results are fabricated.

## Change controls, reset, or swap without API calls

Replace the example path with the audit path printed by your run.

```powershell
python -m src.matchmaker rescore --snapshot data/runs/RUN_ID/audit.json --weights examples/weights.json
python -m src.matchmaker rescore --snapshot data/runs/RUN_ID/audit.json --priorities examples/priorities.json
python -m src.matchmaker rescore --snapshot data/runs/RUN_ID/audit.json --reset
python -m src.matchmaker rescore --snapshot data/runs/RUN_ID/audit.json --swap "@outgoing" "@incoming"
```

Each action creates a new versioned run folder; original files remain unchanged.
Ranking weights and capability priorities are independent, adjustable and
resettable. Priorities are continuous 0-1 values for Reach, Demonstration,
Credibility, Speed; all-zero priorities are allowed. Invalid duplicates, unknown
creators and safety FAIL candidates cannot be swapped in. Coverage/similarity
issues warn rather than block.

Explicit fresh collection:

```powershell
python -m src.matchmaker refresh-data --snapshot data/runs/RUN_ID/audit.json
```

Supply `--trends` again for a verified trend snapshot. Refresh creates a new run
linked to the old one. Re-scoring checks evidence hashes and code/prompt/scoring
versions; a mismatch is reported instead of silently reproducing different logic.

## Locked mechanics

- Discovery deduplicates channels and preserves query/video/rank provenance.
  Credit once per query at its best rank: `1 / log(rank + 1)`, best four queries.
- Gates require a resolvable channel, at least eight usable uploads with statistics,
  and activity within 180 days. Missing statistics remain missing.
- Health is 40% Engagement / 40% Momentum / 20% Activity. Screening blends
  normalized discovery 40% + health 60%, then takes 15 combined + up to 5
  Engagement/Momentum/Activity specialists. Deep model calls happen afterward.
- Audience uses sourced comments, embedding prefiltering, and Gemini quotes with
  validated comment/video IDs. Sampled/usable/prefiltered/cited counts are recorded.
- Safety is metadata-only PASS/REVIEW/FAIL with literal requirement checks and
  Gemini contextual/paraphrase assessment. FAIL is excluded; REVIEW stays visible.
- Brand Fit carries sourced evidence, mismatch direction and consistency.
- Final six dimensions are normalized relative to the frozen shortlist. Missing
  evidence is null and weights renormalize; observed weak evidence is a low score.
- Greedy roster value is 0.50 quality + 0.35 incremental coverage - 0.15 maximum
  similarity. All terms use 0-1 scales. Reach uses median views; Demonstration uses
  test/comparison/how-to view performance relative to other formats; Credibility
  uses comment depth/stated expertise; Speed uses upload frequency.
- Content and comment-language embeddings are mean-pooled separately. Both cosine
  similarities are stored; the pair penalty averages available signals and takes
  the maximum pair against the selected team. This is not shared-viewer measurement.
- Data snapshot, settings, and code/prompt/scoring versions define reproducibility.

Implementation conventions: min-max normalization maps ties to 0.5; the screening
momentum comparison uses the latest five versus up to ten preceding usable uploads
(three preceding at the eight-upload gate). These counts are recorded. Empty
format comparisons contribute no demonstrated coverage. Metadata sufficiency
requires 120 characters. These conventions are explicit, not empirical guarantees.

The two open calibrations are exposed as `--min-comments` (default 10) and
`--reach-exponent` (default 1). Tune them against real evidence, retaining the run
configuration.

## Validation

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m flake8 src tests --select E9,F63,F7,F82
python -m src.matchmaker validate --snapshot data/runs/RUN_ID/audit.json
python -m src.matchmaker validate --snapshot data/runs/RUN_ID/audit.json --repeat-model --output stability.json
python -m src.matchmaker validate --snapshot data/runs/RUN_ID/audit.json --human-ranking blind-ranking.txt
```

Validation includes deterministic replay, all six weights independently +/-10%,
ranking correlations and roster changes. `--repeat-model` evaluates identical
frozen evidence three times (live mode incurs Gemini calls) and reports correlations
and maximum individual rank swing. It does not repull data. Human agreement is
unmeasured until a blind ranking is provided. None of these tests claims predictive
campaign accuracy.

No UI is required. This branch is a backend application; `docs/index.html` is the
existing project page, not a connected campaign interface.
