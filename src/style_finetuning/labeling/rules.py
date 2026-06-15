"""Rule-based weak labeling; intended to be followed by sampled human QA."""

from __future__ import annotations

import re
from typing import Any

TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("economy", ("economy", "jobs", "cost", "budget", "business", "tax", "numbers")),
    ("media", ("media", "report", "headline", "coverage", "press")),
    ("election", ("election", "vote", "ballot", "campaign")),
    ("foreign_policy", ("border", "country", "foreign", "trade", "treaty")),
    ("event", ("meeting", "event", "launch", "conference", "rally")),
    ("education", ("student", "teacher", "school", "education")),
)


def _topic(text: str) -> str:
    lowered = text.lower()
    scores = [
        (sum(lowered.count(keyword) for keyword in keywords), topic)
        for topic, keywords in TOPIC_RULES
    ]
    score, topic = max(scores, default=(0, "other"))
    return topic if score else "other"


def _intent(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("thank", "congratulations", "congrats")):
        return "thank_or_congratulate"
    if any(word in lowered for word in ("critic", "excuse", "unfair", "wrong", "failed")):
        return "criticize_or_rebut"
    if any(word in lowered for word in ("new ", "today", "announce", "report:")):
        return "announce_or_update"
    if any(word in lowered for word in ("great", "fantastic", "beautiful", "achievement")):
        return "praise"
    if "?" in text:
        return "question_or_challenge"
    return "comment"


def _tone_tags(text: str) -> list[str]:
    tags: list[str] = []
    letters = [character for character in text if character.isalpha()]
    uppercase = [character for character in letters if character.isupper()]
    if "!" in text:
        tags.append("emphatic")
    if "?" in text:
        tags.append("rhetorical")
    if letters and len(uppercase) / len(letters) >= 0.15:
        tags.append("uppercase_emphasis")
    if re.search(r"\b(very|great|big|record|tremendous|fantastic)\b", text, re.IGNORECASE):
        tags.append("intensifier")
    if re.search(r"\b(critic|excuse|unfair|wrong|failed)\b", text, re.IGNORECASE):
        tags.append("confrontational")
    return tags or ["neutral"]


def _length_bucket(text: str) -> str:
    words = len(re.findall(r"\S+", text))
    if words <= 8:
        return "very_short"
    if words <= 20:
        return "short"
    if words <= 40:
        return "medium"
    return "long"


def label_post(record: dict[str, Any]) -> dict[str, Any]:
    result = dict(record)
    text = str(record["text_train"])
    result.update(
        {
            "topic": _topic(text),
            "intent": _intent(text),
            "tone_tags": _tone_tags(text),
            "length_bucket": _length_bucket(text),
            "period_bucket": str(record["created_at_utc"])[:7],
        }
    )
    return result
