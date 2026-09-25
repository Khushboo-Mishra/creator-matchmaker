"""Integration tests for combining arithmetic and model dimensions."""
import json

from src import build_scores


def channel_record():
    return {
        "handle": "@studio",
        "title": "Studio",
        "subscribers": 1000,
        "videos": [],
        "sampled_comments": [],
    }


def model_dimensions():
    return {
        dim: {
            "score": score,
            "reason": "model reason",
            "source": "model",
            "evidence": [],
        }
        for dim, score in (
            ("audience_relevance", 8.0),
            ("brand_fit", 7.0),
            ("trend_fit", 6.0),
        )
    }


def test_model_dimensions_are_not_overwritten(monkeypatch, tmp_path):
    channel_path = tmp_path / "studio.json"
    channel_path.write_text(json.dumps(channel_record()))
    scores_path = tmp_path / "scores"

    monkeypatch.setattr(build_scores, "SCORES", scores_path)
    monkeypatch.setattr(build_scores, "RULES_FILE", tmp_path / "rules.md")
    (tmp_path / "rules.md").write_text("rules")
    monkeypatch.setattr(build_scores.arithmetic, "compute", lambda record: {})

    from src import score_ai
    monkeypatch.setattr(
        score_ai,
        "score",
        lambda record, rules: {"dimensions": model_dimensions()},
    )

    output_path = build_scores.build(channel_path, use_model=True)
    output = json.loads(output_path.read_text())

    assert output["dimensions"]["audience_relevance"]["score"] == 8.0
    assert output["dimensions"]["brand_fit"]["score"] == 7.0
    assert output["dimensions"]["trend_fit"]["score"] == 6.0


def test_no_model_populates_null_placeholders(monkeypatch, tmp_path):
    channel_path = tmp_path / "studio.json"
    channel_path.write_text(json.dumps(channel_record()))
    scores_path = tmp_path / "scores"

    monkeypatch.setattr(build_scores, "SCORES", scores_path)
    monkeypatch.setattr(build_scores, "RULES_FILE", tmp_path / "rules.md")
    (tmp_path / "rules.md").write_text("rules")
    monkeypatch.setattr(build_scores.arithmetic, "compute", lambda record: {})

    output_path = build_scores.build(channel_path, use_model=False)
    output = json.loads(output_path.read_text())

    assert output["dimensions"]["audience_relevance"]["score"] is None
    assert output["dimensions"]["brand_fit"]["score"] is None
    assert output["dimensions"]["trend_fit"]["score"] is None
