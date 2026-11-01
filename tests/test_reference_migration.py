from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from src.campaign import Campaign
from src.checkpoint import atomic_write, digest
from src.migrate_checkpoint import migrate, REFERENCE_CODE
from src.pipeline import code_version, run
from src.providers import DemoProvider


@pytest.mark.parametrize("tamper", [False, True])
def test_reference_migration_checks_evidence_and_preserves_completed_work(
    tmp_path, tamper
):
    at = datetime(2026, 10, 26, tzinfo=timezone.utc)
    campaign = Campaign(**json.loads(Path("examples/campaign.json").read_text()))

    class Failing(DemoProvider):
        calls = 0

        def judge(self, *args):
            self.calls += 1
            if self.calls == 2:
                raise ValueError("simulated failure")
            return super().judge(*args)

    source, target = tmp_path / "source", tmp_path / "target"
    with pytest.raises(ValueError, match="simulated failure"):
        run(campaign, Failing(at), at, checkpoint_path=source)
    manifest = json.loads((source / "checkpoint.json").read_text())
    manifest.pop("checksum")
    manifest["bindings"]["code"] = REFERENCE_CODE
    atomic_write(source / "checkpoint.json", dict(manifest, checksum=digest(manifest)))
    bindings = dict(manifest["bindings"], code=code_version())
    if tamper:
        path = next(source.glob("evaluation-*.json"))
        record = json.loads(path.read_text())
        record["value"]["capability_signals"]["demonstration_video_ids"] = ["invented"]
        record["checksum"] = digest(record["value"])
        atomic_write(path, record)
        with pytest.raises(ValueError):
            migrate(source, target, bindings, campaign)
        assert not target.exists()
        return
    before = {p.name: p.read_bytes() for p in source.glob("*")}
    report = migrate(source, target, bindings, campaign)
    assert report["evaluations_reused"] == 1
    assert report["retained_evaluation_prompt_version"] == "metadata-evidence-5"
    assert before == {p.name: p.read_bytes() for p in source.glob("*")}

    class Resume(DemoProvider):
        calls = 0

        def discover(self, *_):
            pytest.fail("No discovery calls")

        def channel(self, *_):
            pytest.fail("No channel calls")

        def judge(self, *args):
            self.calls += 1
            return super().judge(*args)

    provider = Resume(at)
    result = run(campaign, provider, at, checkpoint_path=target, resume=True)
    assert provider.calls == len(result["evaluated"]) - 1
    assert result["checkpoint_migration"] == report
