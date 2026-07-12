"""Stage: Newsletter Generation (spec section 5.8 / 10).

Primary path drafts the newsletter with Groq from structured deal records.
If Groq is unavailable or rate-limited, falls back to a template-based
extractive summary (top-N by credibility score) so the demo never returns an
empty or broken newsletter.
"""
import logging

import config
from src.llm_client import LLMUnavailableError, generate_newsletter

logger = logging.getLogger(__name__)


def _format_deal_line(r: dict) -> str:
    parts = [f"**{r.get('title', 'Untitled')}**"]
    if r.get("acquirer") or r.get("target"):
        who = " → ".join(filter(None, [r.get("acquirer"), r.get("target")]))
        parts.append(f"({who})")
    if r.get("deal_value"):
        currency = r.get("currency") or ""
        parts.append(f"— {currency} {r.get('deal_value')}")
    source = r.get("source", "Unknown")
    url = r.get("url", "")
    parts.append(f"\n  Source: [{source}]({url})")
    return " ".join(parts)


def extractive_fallback(records: list, top_n: int = config.NEWSLETTER_TOP_N) -> str:
    ranked = sorted(records, key=lambda r: r.get("credibility_score") or 0, reverse=True)[:top_n]

    lines = [
        "# FMCG Deal Intelligence Newsletter",
        "*(Generated via extractive fallback — LLM drafting was unavailable for this run.)*",
        "",
        "## Recent Deal Activity",
        "",
    ]
    for r in ranked:
        lines.append(f"- {_format_deal_line(r)}")

    if not ranked:
        lines.append("- No deals met the relevance/credibility bar in this window.")

    return "\n".join(lines)


def build_newsletter(records: list, top_n_fallback: int = config.NEWSLETTER_TOP_N) -> tuple:
    """Returns (newsletter_markdown, used_fallback: bool)."""
    if not records:
        return "# FMCG Deal Intelligence Newsletter\n\nNo qualifying deals found in this window.", False

    try:
        newsletter = generate_newsletter(records)
        return newsletter, False
    except LLMUnavailableError:
        logger.warning("Newsletter LLM unavailable; using extractive fallback")
        return extractive_fallback(records, top_n=top_n_fallback), True


if __name__ == "__main__":
    sample = [
        {"title": "ITC to acquire Prasuma Foods for $150 million", "acquirer": "ITC", "target": "Prasuma Foods",
         "deal_value": 150, "currency": "USD", "credibility_score": 0.91, "source": "Economic Times",
         "url": "https://a.com/1"},
    ]
    text, used_fallback = build_newsletter(sample)
    print(f"used_fallback={used_fallback}\n{text}")
