"""Generic decision engine for workflow automation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class DecisionOutcome(str, Enum):
    """Supported decision outcomes."""

    EXECUTE = "EXECUTE"
    SKIP = "SKIP"
    RETRY = "RETRY"
    DELAY = "DELAY"
    REJECT = "REJECT"


@dataclass(frozen=True, slots=True)
class DecisionInput:
    """Normalized inputs used by every agent-facing decision."""

    research_score: float | None = None
    confidence: float | None = None
    duplicate_detected: bool = False
    category: str | None = None
    user_rules: dict[str, Any] = field(default_factory=dict)
    time_rules: dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class Decision:
    """Decision engine output with explainable reasons."""

    outcome: DecisionOutcome
    reasons: list[str] = field(default_factory=list)
    delay_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "outcome": self.outcome.value,
            "reasons": self.reasons,
            "delay_seconds": self.delay_seconds,
        }


class DecisionEngine:
    """Reusable rule-based decision engine."""

    name = "Decision Engine"
    version = "1.0.0"

    def decide(self, decision_input: DecisionInput) -> Decision:
        """Return a generic automation decision."""
        rules = decision_input.user_rules
        reasons: list[str] = []

        if bool(rules.get("reject")):
            return Decision(DecisionOutcome.REJECT, ["user rule rejected execution"])

        if decision_input.duplicate_detected and not bool(rules.get("allow_duplicates", False)):
            return Decision(DecisionOutcome.SKIP, ["duplicate detected"])

        blocked_categories = set(_as_list(rules.get("blocked_categories")))
        if decision_input.category and decision_input.category in blocked_categories:
            return Decision(DecisionOutcome.REJECT, [f"category blocked: {decision_input.category}"])

        min_score = _float_or_none(rules.get("minimum_score"))
        if min_score is not None and decision_input.research_score is not None:
            if decision_input.research_score < min_score:
                return Decision(DecisionOutcome.SKIP, ["research score below minimum"])

        min_confidence = _float_or_none(rules.get("minimum_confidence"))
        if min_confidence is not None and decision_input.confidence is not None:
            if decision_input.confidence < min_confidence:
                return Decision(DecisionOutcome.RETRY, ["confidence below minimum"])

        max_retries = int(rules.get("max_retries", 3))
        if decision_input.retry_count > max_retries:
            return Decision(DecisionOutcome.REJECT, ["retry limit exceeded"])

        delay_seconds = _time_delay_seconds(decision_input.time_rules, decision_input.created_at)
        if delay_seconds is not None and delay_seconds > 0:
            return Decision(DecisionOutcome.DELAY, ["time rules delayed execution"], delay_seconds)

        reasons.append("all decision rules passed")
        return Decision(DecisionOutcome.EXECUTE, reasons)


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _time_delay_seconds(time_rules: dict[str, Any], now: datetime) -> float | None:
    delay = time_rules.get("delay_seconds")
    if delay not in (None, ""):
        return max(0.0, float(delay))

    not_before = time_rules.get("not_before")
    if isinstance(not_before, str) and not_before:
        target = datetime.fromisoformat(not_before)
        if target.tzinfo is None:
            target = target.replace(tzinfo=UTC)
        return max(0.0, (target - now).total_seconds())

    return None
