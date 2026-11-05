# First live run (PowerShell, from the repository root)

## Current correction: new run required, no migration

Comment sampling now uses the three highest-view videos within the same recent-15
window used by evaluation. Audience explanations describe interests expressed in
sampled comments, never verified viewer occupations or demographics. The report
uses bounded audience wording and retains the original model prose in the audit.
Raw cosine similarity, its penalty, ranking weights and roster formula are unchanged.
Accept the corrected roster even if the previous ranks 1/2/7/5 no longer appear.

Do not resume or migrate live-attempt-1 through live-attempt-4 after this correction.
Historical migration examples below are for older versions only; their collection
compatibility checks now reject the changed sampling method. Keep the original live
run unchanged. Ordinary rescore/export also rejects its older code/prompt version.

Local verification must include tests and a demo run with PDF output before live
spending. A demo with an edited campaign can legitimately have missing synthetic
trend evidence; fixture-backed tests exercise the measured-trend path separately.

After explicit approval of quota spending, use a NEW checkpoint and the existing
campaign-matched discovery/trend inputs. Discovery searches can be skipped, but
channel pulls, newly sampled comments, embeddings and judgments will make API calls.
The previous remaining daily allowance is not a reliable budget for a fresh run.
Check current project quotas first. Do not switch models or silently reuse old
evaluations. The prior roster's unchanged membership under 12 one-at-a-time +/-10%
weight tests is evidence about that old snapshot only, not the corrected run.

Do not share .env or API keys. These steps make paid/quota-consuming calls only
where noted. Live run commands now automatically create a private checkpoint
directory and print its path before collection.

To choose a memorable NEW directory for the next run, append
`--checkpoint data/checkpoints/live-attempt-1` to the run command.
If interrupted or failed, repeat the SAME run command with that checkpoint path
and append `--resume`. Do not start another process against the same checkpoint.
Completed pulls, comments, embeddings and validated evaluations are reused.
The interrupted call or failed evaluation may still need API calls.
Resume freezes the original run time and rejects changes to code, campaign,
discovery, trends, model configuration or calibration. A checksum detects
accidental checkpoint edits; these files are not signed security attestations.
Keep checkpoints private and do not manually modify them. Older failed runs
without checkpoints cannot be resumed. Fresh data requires a new checkpoint.

Model-output validation failures now identify the creator and field. Failed
live evaluations save private evidence and model output under data/diagnostics/
(Git-ignored). These files may contain comment text; do not publish them.
They are diagnostic records, not completed audit snapshots or resume checkpoints.
Scores are never silently clamped or converted. Structured output constraints
reduce malformed responses but do not replace local evidence validation.
Audience evidence is selected by comment ID; the backend copies the full original
comment verbatim. Metadata evidence is selected by passage ID; the backend copies
each original line separately and still applies strict source validation.

### One-time migration after the metadata-evidence fix

The old prompt-version checkpoint cannot resume directly. A narrow migration
checks the approved old code hash, collection implementation, settings and entry
checksums, then copies raw collections/embeddings to a NEW checkpoint:

```powershell
python -m src.migrate_checkpoint --source data/checkpoints/live-attempt-1 --output data/checkpoints/live-attempt-2 --campaign examples/campaign.json --discovery data/discovered_candidates.json --trends data/trends_live.json
```

This makes no API calls. It leaves the original intact, records provenance, and
does NOT reuse completed evaluations from the old prompt. Resume the new directory
using the run command with --checkpoint data/checkpoints/live-attempt-2 --resume.
That resume still spends API quota on evaluations and any uncached work.
Migration refuses an existing output directory. Do not rerun migration after it succeeds.

### One-time migration after the bounded-reference fix

The next fix restricts video, comment and passage selections to supplied IDs.
For the approved metadata-evidence-5 checkpoint only, the migration also verifies
unchanged evaluation/scoring code and rechecks cached evidence against its saved
sources offline. Compatible completed evaluations are retained, with their original
prompt version recorded in migration provenance. Unknown versions are rejected.

```powershell
python -m src.migrate_checkpoint --source data/checkpoints/live-attempt-2 --output data/checkpoints/live-attempt-3 --campaign examples/campaign.json --discovery data/discovered_candidates.json --trends data/trends_live.json
```

This makes no API calls and leaves the source intact. Run it only once; if migration
was already performed for you, skip it. Resume with:

```powershell
python -m src.matchmaker run --campaign examples/campaign.json --mode live --discovery data/discovered_candidates.json --trends data/trends_live.json --checkpoint data/checkpoints/live-attempt-3 --resume
```

Resume still makes calls for unfinished work. Do not edit inputs, model settings,
code or checkpoint files between migration and resume. Structured reference enums
are locally tested, but successful live completion must still be verified.

### One-time migration after embedding rate-limit pacing

New embedding HTTP attempts (including retries) are spaced at least 0.8 seconds
apart, about 75/minute in this process. Cache hits have no added delay. Do not run
multiple pipeline processes: other apps sharing the project also consume quota.
Retries use the larger of the local backoff and Google's Retry-After/RetryInfo
delay. Explicit daily-quota errors and requested waits over 60 seconds stop the
run instead of repeatedly spending requests. Resume later with the same inputs.
Pacing does not increase the daily quota or guarantee against token limits.

For the approved pre-pacing checkpoint, migrate offline once:

```powershell
python -m src.migrate_checkpoint --source data/checkpoints/live-attempt-3 --output data/checkpoints/live-attempt-4 --campaign examples/campaign.json --discovery data/discovered_candidates.json --trends data/trends_live.json
```

The migration rechecks sources, preserves completed evaluations and provenance,
and leaves the original untouched. Skip this if already performed for you.
Resume with the diagnostic launcher to retain useful quota error details:

```powershell
python scripts/run_diagnostic.py run --campaign examples/campaign.json --mode live --discovery data/discovered_candidates.json --trends data/trends_live.json --checkpoint data/checkpoints/live-attempt-4 --resume
```

## 1. Prepare

Activate your existing virtual environment, then:

```powershell
python -m pip install -r requirements.txt
git branch --show-current
```

Use feature/locked-creator-matchmaker. Set GEMINI_API_KEY and YOUTUBE_API_KEY in
.env, and optionally GEMINI_MODEL / GEMINI_EMBEDDING_MODEL. Review and edit
examples/campaign.json BEFORE discovery and trends; both are tied to its fingerprint.

Check configured Gemini models with a small generation and embedding request
(uses Gemini quota/billing). This checks actual access, not just model listings:

```powershell
python -c "import requests; from src.config import GEMINI_API_KEY,GEMINI_MODEL; from src.score_ai import embed_text; r=requests.post('https://generativelanguage.googleapis.com/v1beta/models/'+GEMINI_MODEL+':generateContent',headers={'x-goog-api-key':GEMINI_API_KEY},json={'contents':[{'parts':[{'text':'Reply OK'}]}]},timeout=60); print('Generation HTTP',r.status_code); r.raise_for_status(); assert r.json().get('candidates'); print('Embedding dimensions:',len(embed_text('creative project planning')))"
```

Stop on errors. Do not run discovery until these succeed. Check remaining YouTube
quota in your Google Cloud project; this guide does not promise a fixed run cost.

## 2. Prepare measured trends

The legacy seed_trends command is NOT compatible with the locked pipeline's
verified trend contract. Do not use the synthetic examples/trend_snapshot.json
for live mode.

Optionally propose campaign topics (one Gemini request):

```powershell
python -m src.trends propose --campaign examples/campaign.json --output data/trend_proposals_live.json
```

Download official Google Trends interest-over-time CSVs in English, one topic
per CSV, with at least four complete ordered periods. Store them in data.
Create data/trends_manifest_live.json with this shape, replacing every placeholder:

```json
{
  "campaign_fingerprint": "COPY_FROM_PROPOSALS_OR_COMMAND_BELOW",
  "exports": [
    {
      "file": "YOUR_EXPORTED_FILE.csv",
      "topic": "EXACT_TOPIC_IN_CSV_HEADER",
      "geo": "US",
      "window": "ACTUAL_EXPORT_DATE_RANGE",
      "source_url": "https://trends.google.com/trends/explore?YOUR_ACTUAL_QUERY"
    }
  ]
}
```

Get the fingerprint without API calls:

```powershell
python -c "import json; from pathlib import Path; from src.campaign import Campaign; print(Campaign(**json.loads(Path('examples/campaign.json').read_text())).fingerprint())"
python -m src.trends import --manifest data/trends_manifest_live.json --output data/trends_live.json
```

Import retains checked series and hashes; only measured rises become trend matches.
No rising topics is a valid result. These output commands refuse to overwrite an
existing file: choose a new filename if repeating them.

## 3. Discover once and inspect (Gemini + YouTube calls)

```powershell
python -m src.discover --campaign examples/campaign.json
Get-Content data/discovered_candidates.json
```

This writes/replaces data/discovered_candidates.json. Inspect every query and
the candidate titles, channel IDs and query/rank matches. Stop if irrelevant;
correct the campaign and rediscover intentionally. Old discovery files without a
campaign fingerprint are rejected, rather than silently assigned to this campaign.

## 4. Run using that exact discovery file (YouTube + Gemini calls)

```powershell
python -m src.matchmaker run --campaign examples/campaign.json --mode live --discovery data/discovered_candidates.json --trends data/trends_live.json --no-pdf
```

Discovery is skipped entirely, but channel pulls, comments, embeddings and model
judgments still cost quota. All discovered channels are pulled before screening.
Remove --no-pdf if you want PDF output and ReportLab is installed.
Keep the printed saved-run directory. Do not rerun just to change weights.

## 5. Diagnose and view (no API calls)

Replace RUN_ID with the printed directory name:

```powershell
python -m src.diagnose --snapshot data/runs/RUN_ID/audit.json
python scripts/export_web.py data/runs/RUN_ID/audit.json
python -m http.server 8000 --directory docs
```

Open http://localhost:8000. Review similarity min/median/max/spread, observed versus
expected pair count, each pick's individual rank and coverage gain, missing evidence
and safety warnings. A top-four roster is a finding, not a failure. Do not rescale
similarity or change weights simply to manufacture a different team.

Diagnostics accept older snapshots and explicitly do NOT certify integrity.
Export/rescore retain the stricter code-version and integrity checks.
Exported display fields become public if you push docs/data.js; inspect first.

To revise weights without external calls:

```powershell
python -m src.matchmaker rescore --snapshot data/runs/RUN_ID/audit.json --weights examples/weights.json --no-pdf
```

This saves a new run while preserving the original. Use its new audit.json for
diagnosis/export. Data refresh is a separate, deliberate API-consuming operation.
