# Reproduce the published demo

From the repository root:

```powershell
python -m src.matchmaker run --campaign examples/campaign.json --mode demo --no-pdf
python scripts/export_web.py data/runs/<printed-run-id>/audit.json
python -m http.server 8000 --directory docs
```

Open http://localhost:8000. The initial roster is the saved backend roster.
Sliders and removals are unsaved local previews; Restore saved run resets them.
The export includes public titles, explanations, scores, similarities and run metadata,
not raw comments or embeddings. Inspect it before publishing a live run.
If data.js cannot load, the page explicitly labels its historical fallback.

The sample campaign automatically loads examples/trend_snapshot.json in demo mode.
Its dated search links and invented measurements are fixtures, not verified Google
Trends evidence. Live mode rejects synthetic trend snapshots. Other campaigns need
their own matching snapshot; --trends overrides the demo default.

Scoring version locked-3 chooses the first creator by individual quality alone.
Later picks use 0.50 quality + 0.35 added coverage - 0.15 maximum similarity.
Coverage is normalized by the sum of priorities (zero priorities give zero gain).
Scaling every priority equally no longer changes coverage; their relative values
still matter. Demo capability spread is illustrative, not calibration on real data.

Run Python tests with python -m pytest -q and web checks with node --test tests/test_web.cjs.
