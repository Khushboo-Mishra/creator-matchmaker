"""Plain-language marketer report, distinct from the full internal audit JSON."""

from html import escape
from pathlib import Path


def audience_summary(evidence):
    """Do not publish unrestricted model prose as audience composition facts."""
    counts = evidence.get("counts", {})
    usable = counts.get("usable", 0)
    if evidence["score"] is None:
        assessment = (
            "Not enough usable sourced comments to assess campaign-interest relevance."
        )
    else:
        assessment = (
            f"Campaign-interest score from sampled comments: {evidence['score'] * 10:.1f}/10. "
            "This is a model judgment about expressed interests, not a verified fact about viewers."
        )
    return (
        assessment
        + f" Usable sourced comments: {usable}; cited comments: {len(evidence['evidence'])}. "
        "The sample does not establish viewers' occupations or demographics, or represent the whole audience. "
        "Any quoted self-description is an unverified individual statement."
    )


def report_sections(run):
    sections = [
        ("Creator Matchmaker", f"Campaign: {run['campaign']['product_description']}"),
        ("Goal", run["campaign"]["specific_goal"]),
        ("Data date", run["data_snapshot_at"]),
    ]
    if run["mode"] != "live":
        sections.append(
            (
                "Synthetic demo",
                "These creators and judgments are test fixtures, not real recommendations.",
            )
        )
    sections.append(
        (
            "Recommended team",
            "; ".join(c["title"] + " (" + c["handle"] + ")" for c in run["roster"]),
        )
    )
    selected = {c["handle"] for c in run["roster"]}
    for index, creator in enumerate(run["roster"], 1):
        role = max(creator["capabilities"], key=creator["capabilities"].get)
        sections.append(
            (
                f"{index}. {creator['title']} ({creator['handle']})",
                f"Suggested role: {role.capitalize()}.",
            )
        )
        quotes = []
        for d in ("audience_relevance", "brand_fit", "trend_fit"):
            evidence = creator["raw_dimensions"][d]
            sections.append(
                (
                    d.replace("_", " ").title(),
                    (
                        audience_summary(evidence)
                        if d == "audience_relevance"
                        else evidence["reason"]
                    ),
                )
            )
            for item in evidence["evidence"][:2]:
                if "quote" in item:
                    quote = (
                        item["quote"]
                        + " | "
                        + item.get("url", "Video: " + item.get("video_id", ""))
                    )
                    if quote not in quotes:
                        quotes.append(quote)
        if quotes:
            sections.append(("Supporting evidence", quotes))
        components = creator["marginal_components"]
        sections.append(
            (
                "Why included",
                (
                    "Adds capability coverage to the team."
                    if components["coverage_gain"] > 0
                    else "Selected for individual campaign suitability."
                ),
            )
        )
        comparison = creator.get("comparison")
        if comparison:
            other = comparison["alternative_components"]
            strengths = []
            if components["quality"] > other["quality"]:
                strengths.append("stronger individual campaign fit")
            if components["coverage_gain"] > other["coverage_gain"]:
                strengths.append("more additional team capability")
            if components["max_similarity"] < other["max_similarity"]:
                strengths.append("less duplication with earlier picks")
            reason = (
                ", ".join(strengths)
                if strengths
                else "a strategist choice or deterministic tie-break"
            )
            sections.append(
                (
                    "Compared with " + comparison["alternative"],
                    "This selection reflects " + reason + ".",
                )
            )
        if creator["brand_safety"] == "REVIEW":
            sections.append(("Review before outreach", creator["safety_reason"]))
        if creator["missing_dimensions"]:
            sections.append(
                (
                    "Evidence limits",
                    "Not enough information for: "
                    + ", ".join(
                        d.replace("_", " ") for d in creator["missing_dimensions"]
                    ),
                )
            )
    alternatives = [
        c
        for c in run["ranking"]
        if c["handle"] not in selected
        and c["brand_safety"] != "FAIL"
        and c["combined_score"] is not None
    ][:3]
    if alternatives:
        sections.append(
            (
                "Next-best alternatives",
                [
                    f"{c['title']} ({c['handle']}): {c['raw_dimensions']['brand_fit']['reason']}"
                    for c in alternatives
                ],
            )
        )
    if run["warnings"]:
        sections.append(
            (
                "Warnings to review",
                [w.replace("_", " ") for w in run["warnings"]],
            )
        )
    sections.append(
        (
            "How the team is chosen",
            "The first automatic pick uses individual quality alone; picks two to four balance quality, added capability coverage and similarity, so their selection totals are not directly comparable with the first pick's total. Manual swaps reflect the marketer's choice.",
        )
    )
    sections.append(
        (
            "Method and limitations",
            "Creators were screened for recent measurable activity, then evaluated on six campaign dimensions. Team selection balances suitability, capability coverage and similarity. Missing evidence is excluded from scoring. Rankings are relative to this shortlist, not comparable across campaigns. Comments are an audience-interest proxy, not demographics. Safety and capability judgments use metadata, not watched videos. Similarity is a content/comment-language proxy, not measured audience overlap. Availability, rates and campaign outcomes are not verified.",
        )
    )
    return sections


def heading_levels(sections):
    in_creator = False
    for title, text in sections:
        if title.split(".")[0].isdigit():
            in_creator = True
            level = 2
        elif title in (
            "Next-best alternatives",
            "Warnings to review",
            "Method and limitations",
            "How the team is chosen",
        ):
            in_creator = False
            level = 2
        else:
            level = 1 if title == "Creator Matchmaker" else (3 if in_creator else 2)
        yield level, title, text


def write_reports(run, directory, pdf=True):
    directory = Path(directory)
    sections = report_sections(run)
    (directory / "report.md").write_text(
        "\n\n".join(
            "#" * level
            + " "
            + title
            + "\n\n"
            + (
                "\n".join("- " + item for item in text)
                if isinstance(text, list)
                else text
            )
            for level, title, text in heading_levels(sections)
        ),
        encoding="utf-8",
    )
    if not pdf:
        return
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        PageBreak,
        KeepTogether,
    )

    styles = getSampleStyleSheet()
    styles["Heading3"].keepWithNext = True
    styles["BodyText"].alignment = TA_LEFT
    styles["BodyText"].leading = 13
    flow = []
    for level, title, text in heading_levels(sections):
        if title.split(".")[0].isdigit() or title == "Next-best alternatives":
            flow.append(PageBreak())
        flow.append(
            KeepTogether(
                [
                    Paragraph(
                        escape(title),
                        styles[f"Heading{level}"],
                    ),
                    *[
                        Paragraph(
                            escape(item),
                            styles["BodyText"],
                            bulletText="•" if isinstance(text, list) else None,
                        )
                        for item in (text if isinstance(text, list) else [text])
                    ],
                    Spacer(1, 4),
                ]
            )
        )

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(
            48,
            24,
            "Creator Matchmaker | Sampled evidence, not verified audience demographics",
        )
        canvas.drawRightString(doc.pagesize[0] - 48, 24, str(doc.page))
        canvas.restoreState()

    SimpleDocTemplate(
        str(directory / "report.pdf"),
        rightMargin=48,
        leftMargin=48,
        topMargin=40,
        bottomMargin=40,
    ).build(flow, onFirstPage=footer, onLaterPages=footer)
