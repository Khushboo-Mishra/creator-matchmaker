"""Give model-selectable IDs to verbatim metadata passages."""


def passages(metadata):
    result = []
    for source_index, source in enumerate(metadata):
        for line_index, line in enumerate(source["text"].splitlines()):
            if line.strip():
                result.append(
                    {
                        "passage_id": f"m{source_index}-l{line_index}",
                        "video_id": source["video_id"],
                        "text": line,
                    }
                )
    return result


def resolve_metadata(result, supplied):
    by_id = {p["passage_id"]: p for p in supplied}
    for section in ("brand_fit", "safety", "capabilities"):
        resolved, seen = [], set()
        for selection in result[section]["evidence"]:
            passage_id = selection["passage_id"]
            if passage_id not in by_id:
                raise ValueError(
                    f"{section}: unknown metadata passage_id {passage_id!r}"
                )
            if passage_id in seen:
                continue
            seen.add(passage_id)
            source = by_id[passage_id]
            resolved.append({"video_id": source["video_id"], "quote": source["text"]})
        result[section]["evidence"] = resolved
    return result
