from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from src.campaign import Campaign
from src.checkpoint import Checkpoint
from src.pipeline import run
from src.providers import DemoProvider

AT = datetime(2026, 10, 26, tzinfo=timezone.utc)


def test_resume_reuses_completed_work(tmp_path):
    campaign = Campaign(**json.loads(Path("examples/campaign.json").read_text()))

    class Failing(DemoProvider):
        calls = 0

        def judge(self, *args):
            self.calls += 1
            if self.calls == 2:
                raise ValueError("simulated failure")
            return super().judge(*args)

    checkpoint = tmp_path / "checkpoint"
    with pytest.raises(ValueError, match="simulated failure"):
        run(campaign, Failing(AT), AT, checkpoint_path=checkpoint)
    assert len(list(checkpoint.glob("evaluation-*.json"))) == 1

    class Resume(DemoProvider):
        calls = 0

        def discover(self, *_):
            pytest.fail("Discovery already saved")

        def channel(self, *_):
            pytest.fail("Channel pulls already saved")

        def judge(self, *args):
            self.calls += 1
            return super().judge(*args)

    provider = Resume(AT)
    result = run(campaign, provider, AT, checkpoint_path=checkpoint, resume=True)
    assert provider.calls == len(result["evaluated"]) - 1

    class NoCalls(Resume):
        def comments(self, *_):
            pytest.fail("No comments")

        def embed(self, *_):
            pytest.fail("No embeddings")

        def judge(self, *_):
            pytest.fail("No judgments")

    replay = run(
        campaign,
        NoCalls(AT),
        datetime(2026, 11, 1, tzinfo=timezone.utc),
        checkpoint_path=checkpoint,
        resume=True,
    )
    assert replay["data_snapshot_at"] == result["data_snapshot_at"]
    assert replay["ranking"] == result["ranking"]
    assert replay["roster"] == result["roster"]


def test_binding_integrity_and_existing_directory(tmp_path):
    path = tmp_path / "check"
    cache = Checkpoint(path, {"model": "a"}, AT)
    with pytest.raises(FileExistsError):
        Checkpoint(path, {"model": "a"}, AT)
    with pytest.raises(ValueError, match="changed"):
        Checkpoint(path, {"model": "b"}, AT, resume=True)
    cache.call("embedding", "text", lambda: [1, 2])
    entry = next(path.glob("embedding-*.json"))
    value = json.loads(entry.read_text())
    value["value"] = [99]
    entry.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="integrity"):
        cache.call("embedding", "text", lambda: pytest.fail("No API"))


def test_failed_call_not_cached(tmp_path):
    cache = Checkpoint(tmp_path / "check", {}, AT)

    def fail():
        raise ValueError("invalid")

    with pytest.raises(ValueError):
        cache.call("evaluation", {}, fail)
    assert not list(cache.directory.glob("evaluation-*.json"))
    assert cache.call("evaluation", {}, lambda: {"valid": True}) == {"valid": True}


def test_cli_resume_saves_new_audit_without_modifying_first(tmp_path):
    from src.matchmaker import main

    checkpoint = tmp_path / "cli-checkpoint"
    output = tmp_path / "runs"
    args = [
        "run",
        "--campaign",
        "examples/campaign.json",
        "--mode",
        "demo",
        "--checkpoint",
        str(checkpoint),
        "--out",
        str(output),
        "--no-pdf",
    ]
    main(args)
    original = next(output.glob("*/audit.json"))
    content = original.read_bytes()
    main(args + ["--resume"])
    assert len(list(output.glob("*/audit.json"))) == 2
    assert original.read_bytes() == content


def test_cli_resume_requires_checkpoint():
    from src.matchmaker import main

    with pytest.raises(ValueError, match="requires --checkpoint"):
        main(
            [
                "run",
                "--campaign",
                "examples/campaign.json",
                "--mode",
                "demo",
                "--resume",
                "--no-pdf",
            ]
        )
