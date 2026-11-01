from datetime import datetime, timezone
import json

import pytest

from src.metadata_evidence import passages, resolve_metadata
from src.checkpoint import Checkpoint, digest, atomic_write
from src.migrate_checkpoint import migrate, LEGACY_CODE
from src.pipeline import code_version


def test_separate_chapter_passages_are_verbatim():
    source = [
        {
            "video_id": "v",
            "text": "Heading\n0:43 Script Implementing \n1:48 Shot List\n\n3:41 Storyboards",
        }
    ]
    supplied = passages(source)
    assert [p["passage_id"] for p in supplied] == ["m0-l0", "m0-l1", "m0-l2", "m0-l4"]
    result = {
        s: {"evidence": [{"passage_id": "m0-l1"}, {"passage_id": "m0-l2"}]}
        for s in ("brand_fit", "safety", "capabilities")
    }
    resolved = resolve_metadata(result, supplied)
    assert resolved["capabilities"]["evidence"] == [
        {"video_id": "v", "quote": "0:43 Script Implementing "},
        {"video_id": "v", "quote": "1:48 Shot List"},
    ]
    for section in resolved.values():
        assert all(e["quote"] in source[0]["text"] for e in section["evidence"])


def test_unknown_metadata_id_rejected():
    result = {
        s: {"evidence": [{"passage_id": "invented"}]}
        for s in ("brand_fit", "safety", "capabilities")
    }
    with pytest.raises(ValueError, match="unknown metadata passage_id"):
        resolve_metadata(result, [])


@pytest.fixture
def legacy(tmp_path):
    bindings = {"code": LEGACY_CODE, "model": "test"}
    cache = Checkpoint(
        tmp_path / "old", bindings, datetime(2026, 11, 1, tzinfo=timezone.utc)
    )
    cache.call("channel", {"id": 1}, lambda: {"id": 1})
    cache.call("embedding", "text", lambda: [1, 2])
    cache.call("evaluation", {"id": 1}, lambda: {"old": True})
    return cache, dict(bindings, code=code_version()), tmp_path / "new"


def test_migration_preserves_source_and_copies_only_compatible_work(legacy):
    cache, bindings, destination = legacy
    before = {p.name: p.read_bytes() for p in cache.directory.glob("*")}
    report = migrate(cache.directory, destination, bindings)
    assert report["evaluations_not_reused"] == 1
    assert report["copied"] == {"channel": 1, "embedding": 1}
    assert not list(destination.glob("evaluation-*.json"))
    assert before == {p.name: p.read_bytes() for p in cache.directory.glob("*")}
    resumed = Checkpoint(destination, bindings, datetime.now(timezone.utc), resume=True)
    assert resumed.migration == report
    assert resumed.call("channel", {"id": 1}, lambda: pytest.fail("No API")) == {
        "id": 1
    }
    assert resumed.call("evaluation", {"id": 1}, lambda: {"new": True}) == {"new": True}
    with pytest.raises(ValueError, match="new directory"):
        migrate(cache.directory, destination, bindings)


@pytest.mark.parametrize("kind", ["model", "entry", "manifest", "code"])
def test_migration_fails_closed_before_writes(legacy, kind):
    cache, bindings, destination = legacy
    if kind == "model":
        bindings["model"] = "different"
    elif kind == "entry":
        path = next(cache.directory.glob("embedding-*.json"))
        data = json.loads(path.read_text())
        data["value"] = [99]
        path.write_text(json.dumps(data))
    else:
        path = cache.directory / "checkpoint.json"
        data = json.loads(path.read_text())
        data["bindings"]["code"] = "unknown"
        if kind == "code":
            data.pop("checksum")
            data["checksum"] = digest(data)
        atomic_write(path, data)
    with pytest.raises(ValueError):
        migrate(cache.directory, destination, bindings)
    assert not destination.exists()
