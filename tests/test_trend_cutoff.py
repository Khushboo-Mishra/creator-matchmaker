import hashlib
import json

import pytest

from src.trends import import_exports, main


@pytest.fixture
def files(tmp_path):
    path = tmp_path / "source.csv"
    path.write_text(
        "Week,planning: (United States)\n2026-09-27,10\n2026-10-04,20\n2026-10-11,40\n2026-10-18,60\n2026-10-25,0\n2026-11-01,0\n"
    )
    manifest = {
        "campaign_fingerprint": "test",
        "exports": [
            {
                "file": path.name,
                "topic": "planning",
                "geo": "US",
                "window": "original export window",
                "source_url": "https://trends.google.com/trends/explore?q=planning",
            }
        ],
    }
    return path, manifest


def test_cutoff_preserves_original_and_records_exclusions(files):
    path, manifest = files
    original = path.read_bytes()
    result = import_exports(manifest, path.parent, before="2026-10-25")
    record = result["checked_topics"][0]
    assert record["excluded_dates"] == ["2026-10-25", "2026-11-01"]
    assert record["previous_interest"] == 15
    assert record["recent_interest"] == 50
    assert record["retained_period_start_range"]["last"] == "2026-10-18"
    assert record["export_sha256"] == hashlib.sha256(original).hexdigest()
    assert path.read_bytes() == original
    assert result["filter"]["before"] == "2026-10-25"
    assert (
        import_exports(manifest, path.parent, before="2026-10-25")["checked_topics"]
        == result["checked_topics"]
    )


@pytest.mark.parametrize(
    "before", ["bad", "2026-02-30", "2026-1-2", "2026-10-25T00:00:00"]
)
def test_invalid_cutoff(files, before):
    path, manifest = files
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        import_exports(manifest, path.parent, before=before)


def test_insufficient_retained_periods(files):
    path, manifest = files
    with pytest.raises(ValueError, match="retained"):
        import_exports(manifest, path.parent, before="2026-10-18")


def test_without_cutoff_and_no_exclusions(files):
    path, manifest = files
    all_rows = import_exports(manifest, path.parent)["checked_topics"]
    assert len(all_rows[0]["series"]) == 6
    assert all_rows[0]["excluded_dates"] == []
    assert (
        import_exports(manifest, path.parent, before="2027-01-01")["checked_topics"]
        == all_rows
    )


def test_cli_cutoff_and_no_overwrite(files):
    path, manifest = files
    manifest_path = path.parent / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    output = path.parent / "snapshot.json"
    args = [
        "import",
        "--manifest",
        str(manifest_path),
        "--output",
        str(output),
        "--before",
        "2026-10-25",
    ]
    main(args)
    assert json.loads(output.read_text())["filter"]["before"] == "2026-10-25"
    with pytest.raises(FileExistsError):
        main(args)


def test_accepts_current_google_trends_export_format(tmp_path):
    """The live export writes "Time" and a bare topic, not "Week" and
    "topic: (United States)". Both shapes must import; this is the one
    that actually comes out of trends.google.com today."""
    csv_text = (
        '"Time","mood board"\n'
        '"2025-11-02",80\n'
        '"2025-11-09",78\n'
        '"2025-11-16",84\n'
        '"2025-11-23",64\n'
        '"2025-11-30",95\n'
        '"2025-12-07",98\n'
    )
    (tmp_path / "t.csv").write_text(csv_text, encoding="utf-8")
    manifest = {
        "campaign_fingerprint": "f" * 64,
        "exports": [{
            "file": "t.csv",
            "topic": "mood board",
            "geo": "US",
            "window": "2025-11-02 to 2025-12-07",
            "source_url": "https://trends.google.com/trends/explore?geo=US&q=mood%20board",
        }],
    }
    result = import_exports(manifest, tmp_path)
    assert result["checked_topics"][0]["topic"] == "mood board"
    assert len(result["checked_topics"][0]["series"]) == 6
    assert result["trends"], "a rising second half must be detected"


def test_rejects_topic_that_does_not_match_the_bare_header(tmp_path):
    (tmp_path / "t.csv").write_text(
        '"Time","mood board"\n"2025-11-02",1\n"2025-11-09",2\n'
        '"2025-11-16",3\n"2025-11-23",4\n',
        encoding="utf-8",
    )
    manifest = {
        "campaign_fingerprint": "f" * 64,
        "exports": [{
            "file": "t.csv",
            "topic": "storyboard",
            "geo": "US",
            "window": "w",
            "source_url": "https://trends.google.com/trends/explore?geo=US&q=storyboard",
        }],
    }
    try:
        import_exports(manifest, tmp_path)
    except ValueError as exc:
        assert "does not match" in str(exc)
    else:
        raise AssertionError("mismatched topic must be rejected")
