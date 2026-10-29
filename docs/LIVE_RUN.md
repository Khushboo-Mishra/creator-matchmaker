# First live run (PowerShell, from the repository root)

Do not share .env or API keys. These steps make paid/quota-consuming calls only
where noted. There is no automatic resume after a failed live run.

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
