from copy import deepcopy

import pytest
from jsonschema import validate, ValidationError

from src.judgment_contract import schema_for_trends
from src.reference_schema import bind_references


def test_reference_choices_are_bounded_without_mutating_source():
    original = schema_for_trends(None)
    before = deepcopy(original)
    schema = bind_references(
        original,
        [{"video_id": "7gpm4NWzaGU"}, {"video_id": "channel-description"}],
        [{"comment_id": "c1"}],
        [{"passage_id": "m0-l0"}],
    )
    props = schema["properties"]
    demos = props["capabilities"]["properties"]["demonstration_video_ids"]
    validate(["7gpm4NWzaGU"], demos)
    for bad in ("12gpm4NWzaGU", "channel-description"):
        with pytest.raises(ValidationError):
            validate([bad], demos)
    assert props["audience"]["properties"]["quotes"]["items"]["properties"][
        "comment_id"
    ]["enum"] == ["c1"]
    for section in ("brand_fit", "safety", "capabilities"):
        assert props[section]["properties"]["evidence"]["items"]["properties"][
            "passage_id"
        ]["enum"] == ["m0-l0"]
    trend_videos = props["trend_matches"]["items"]["properties"]["video_ids"]
    validate(["7gpm4NWzaGU"], trend_videos)
    with pytest.raises(ValidationError):
        validate([], trend_videos)
    assert original == before


def test_empty_sources_force_empty_selections():
    props = bind_references(schema_for_trends(None), [], [], [])["properties"]
    arrays = [
        props["audience"]["properties"]["quotes"],
        props["capabilities"]["properties"]["demonstration_video_ids"],
        props["trend_matches"],
    ]
    arrays += [
        props[s]["properties"]["evidence"]
        for s in ("brand_fit", "safety", "capabilities")
    ]
    for array in arrays:
        validate([], array)
        assert array["maxItems"] == 0
