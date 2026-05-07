from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import settings
from app.schemas.signal import SignalContract

logger = logging.getLogger(__name__)


Decision = Literal["approve", "reject", "needs_more_data"]


@dataclass(frozen=True)
class TradingAgentsReview:
    score: float
    decision: Decision
    critique: str


class TradingAgentsReviewer:
    """Optional LLM-based reviewer using the `tradingagents` LLM wrapper.

    This is deliberately lightweight: it does NOT require running the full
    tradingagents graph; it uses their unified chat-model builder and a strict
    JSON response contract.
    """

    def __init__(self) -> None:
        self.enabled = bool(settings.tradingagents_enabled)
        self.mode_a = bool(settings.tradingagents_mode_a_enabled)
        self.mode_b = bool(settings.tradingagents_mode_b_enabled)
        self.gate_min_score = float(settings.tradingagents_gate_min_score)

        self._llm = None
        if not self.enabled:
            return

        try:
            from tradingagents.llm import build_chat_model  # type: ignore
        except Exception as exc:
            logger.warning("TradingAgents not available: %s", exc)
            self.enabled = False
            return

        provider = str(settings.tradingagents_provider).strip()
        model = str(settings.tradingagents_model).strip()
        effort = str(settings.tradingagents_reasoning_effort).strip() or None

        try:
            self._llm = build_chat_model(
                provider=provider,  # type: ignore[arg-type]
                model=model,
                reasoning_effort=effort,  # type: ignore[arg-type]
            )
        except Exception as exc:
            logger.warning("Failed to initialize TradingAgents LLM: %s", exc)
            self.enabled = False

    def review(
        self,
        *,
        signal: SignalContract,
        risk_note: str,
        limits_note: str,
        context: str,
    ) -> TradingAgentsReview | None:
        if not self.enabled or not self._llm:
            return None

        prompt = self._build_prompt(
            signal=signal,
            risk_note=risk_note,
            limits_note=limits_note,
            context=context,
        )

        try:
            # LangChain-style ChatModel: `.invoke(str)` returns message-like object.
            resp = self._llm.invoke(prompt)
            content = getattr(resp, "content", resp)
            if not isinstance(content, str):
                content = str(content)
            data = self._parse_json(content)
            return TradingAgentsReview(
                score=float(data.get("score", 0.0)),
                decision=self._normalize_decision(data.get("decision")),
                critique=str(data.get("critique", "")).strip(),
            )
        except Exception as exc:
            logger.warning("TradingAgents review failed: %s", exc)
            return None

    def gate(self, review: TradingAgentsReview) -> tuple[bool, str]:
        """Mode B: returns (allowed, reason)."""
        if not self.mode_b:
            return True, "gate_disabled"

        if review.score < self.gate_min_score:
            return False, f"agent_score_below_threshold({review.score:.1f}<{self.gate_min_score:.1f})"

        if review.decision == "reject":
            return False, "agent_rejected"

        if review.decision == "needs_more_data":
            return False, "agent_needs_more_data"

        return True, "agent_approved"

    def format_for_explanation(self, review: TradingAgentsReview) -> str:
        score = f"{review.score:.1f}"
        return (
            "\n\n🧪 TradingAgents Review\n"
            f"- Score: {score}/100\n"
            f"- Decision: {review.decision}\n"
            f"- Critique: {review.critique}"
        )

    def _build_prompt(
        self,
        *,
        signal: SignalContract,
        risk_note: str,
        limits_note: str,
        context: str,
    ) -> str:
        # Strict JSON contract makes downstream handling reliable.
        return (
            "You are a skeptical trading signal reviewer.\n"
            "Your job: critique the proposed trade, identify missing info, and decide whether it should be broadcast.\n\n"
            "Return ONLY valid JSON with keys:\n"
            '- "score": number 0-100 (higher = better)\n'
            '- "decision": one of "approve", "reject", "needs_more_data"\n'
            '- "critique": short paragraph (max 600 chars)\n\n'
            "Signal:\n"
            f"- symbol: {signal.symbol}\n"
            f"- timeframe: {signal.timeframe}\n"
            f"- direction: {signal.signal.value}\n"
            f"- entry: {signal.entry_price}\n"
            f"- stop_loss: {signal.stop_loss}\n"
            f"- take_profit: {signal.take_profit}\n"
            f"- confidence: {signal.confidence}\n"
            f"- reason: {signal.reason}\n\n"
            "Risk engine notes:\n"
            f"- risk_note: {risk_note}\n"
            f"- limits_note: {limits_note}\n\n"
            "Retrieved context (may be empty):\n"
            f"{context}\n"
        )

    def _parse_json(self, content: str) -> dict[str, Any]:
        # Be robust to accidental markdown fences.
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
        # Find first/last braces if model returns extra prose.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
        return json.loads(text)

    def _normalize_decision(self, value: Any) -> Decision:
        v = str(value or "").strip().lower()
        if v in ("approve", "approved", "allow", "ok"):
            return "approve"
        if v in ("reject", "rejected", "deny", "no"):
            return "reject"
        return "needs_more_data"

