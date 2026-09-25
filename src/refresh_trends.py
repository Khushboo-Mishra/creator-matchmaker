"""Explicitly refresh the Search-grounded trend snapshot for this campaign.

Usage:
    python -m src.refresh_trends
"""
from .score_ai import refresh_trend_topics


def main():
    context, citations = refresh_trend_topics()
    print("Updated data/trend_snapshot.json")
    print(f"Grounded context: {len(context)} characters")
    print(f"Citations: {len(citations)}")


if __name__ == "__main__":
    main()
