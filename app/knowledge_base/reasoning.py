"""AI reasoning engine — builds explanations from knowledge base context.

Uses the provider-agnostic LLM client (OpenAI / DeepSeek / Anthropic) for all
chat completions. When no provider is configured or a request fails, the
engine returns deterministic rule-based output so the pipeline never blocks.
"""

from __future__ import annotations

import logging
from typing import Any

from app.schemas.signal import SignalContract
from app.services.llm_client import chat_complete, configured_provider

logger = logging.getLogger(__name__)


class ReasoningEngine:
    """Generate signal explanations using knowledge base context.

    Output is advisory only and must never gate execution decisions.
    """

    @property
    def provider(self) -> dict[str, str]:
        return configured_provider()

    def explain(self, signal: SignalContract, context: str) -> str:
        """Return a human-readable explanation of the signal."""
        refined_context = self.synthesize_lessons(context) if context else ""
        prompt = self._build_explain_prompt(signal, refined_context)
        text = chat_complete(prompt, max_tokens=200, temperature=0.3)
        if text:
            return text
        return self._rule_based_explain(signal, refined_context)

    def synthesize_lessons(self, raw_context: str) -> str:
        """Clean and synthesize raw RAG retrieval into a cohesive context block."""
        if not raw_context:
            return ""
        lines = [line.strip("- ") for line in raw_context.split("\n") if line.strip()]
        unique_lines = list(dict.fromkeys(lines))[:5]
        return "\n".join(f"- {line}" for line in unique_lines)

    def _build_explain_prompt(self, signal: SignalContract, context: str) -> str:
        prompt = (
            "You are an expert crypto trading analyst. Your task is to explain a "
            "signal using the given context.\n\n"
            "--- SIGNAL DATA ---\n"
            f"Pair: {signal.symbol} | Timeframe: {signal.timeframe} | "
            f"Type: {signal.signal.value}\n"
            f"Entry: {signal.entry_price:.2f} | "
            f"SL: {signal.stop_loss:.2f} | "
            f"TP: {signal.take_profit:.2f}\n"
            f"Strategy Reason: {signal.reason}\n"
            f"Confidence: {signal.confidence:.1f}%\n"
        )
        if context:
            prompt += (
                "\n--- PAST LEARNED LESSONS & RELEVANT STRATEGY CONTEXT ---\n"
                f"{context}\n"
                "\nSynthesize the above context into your explanation if relevant. "
                "If the context warns against this type of setup, mention it."
            )
        prompt += "\nProvide a concise 2-3 sentence explanation."
        return prompt

    def _rule_based_explain(self, signal: SignalContract, context: str) -> str:
        rr = abs(signal.take_profit - signal.entry_price) / max(
            abs(signal.entry_price - signal.stop_loss), 1e-9
        )
        parts = [
            f"Signal: {signal.signal.value} on {signal.symbol} ({signal.timeframe}).",
            f"Strategy reason: {signal.reason}.",
            f"Risk-reward ratio: {rr:.2f}.",
            f"Confidence: {signal.confidence:.1f}%.",
        ]
        if context:
            parts.append(f"Context: {context[:200]}")
        parts.append("This analysis is advisory only; risk rules remain authoritative.")
        return " ".join(parts)

    def analyze_simulation_result(self, result: Any) -> str:
        """Analyze an optimization/backtest result and return a concise lesson."""
        prompt = (
            f"You are a quant analyst. Analyze this optimization result for "
            f"{result.strategy} on {result.symbol}.\n"
            f"Best Sharpe: {result.best_sharpe:.2f} | "
            f"Return: {result.best_return_pct:.1f}%\n"
            f"Best Params: {result.best_params}\n"
            f"Total Sims: {result.total_simulations}\n\n"
            f"Extract ONE CRITICAL LESSON (max 20 words) about why this "
            f"configuration performed well."
        )
        text = chat_complete(prompt, max_tokens=100, temperature=0.3)
        if text:
            return text.strip('"')
        return self._rule_based_analyze_simulation(result)

    def _rule_based_analyze_simulation(self, result: Any) -> str:
        return (
            f"Strategy {result.strategy} on {result.symbol} achieved "
            f"{result.best_sharpe:.2f} Sharpe with params {result.best_params} "
            f"over {result.total_simulations} simulations."
        )

    def analyze_trade_outcome(self, outcome: dict) -> str:
        """Analyze a closed trade and return a single-sentence lesson."""
        prompt = (
            f"You are a quant trading bot analyzing a just-closed paper trade.\n"
            f"Pair: {outcome.get('symbol')}\n"
            f"Direction: {outcome.get('direction')}\n"
            f"Reason for close: {outcome.get('reason')}\n"
            f"ROI: {outcome.get('roi_percent', 0.0):.2f}%\n"
            f"Duration: {outcome.get('duration_seconds', 0.0) / 60:.1f} minutes\n\n"
            f"Write exactly ONE SENTENCE summarizing the lesson learned from "
            f"this specific setup."
        )
        text = chat_complete(prompt, max_tokens=100, temperature=0.3)
        if text:
            return text.strip('"')
        return self._rule_based_analyze_trade_outcome(outcome)

    def _rule_based_analyze_trade_outcome(self, outcome: dict) -> str:
        target = (
            "hit take profit"
            if outcome.get("reason") == "TAKE_PROFIT"
            else "stopped out"
        )
        return (
            f"A {outcome.get('direction', 'TRADE')} on "
            f"{outcome.get('symbol', 'UNKNOWN')} {target} for "
            f"{outcome.get('roi_percent', 0.0):.2f}% after "
            f"{outcome.get('duration_seconds', 0.0) / 60:.1f} minutes."
        )
