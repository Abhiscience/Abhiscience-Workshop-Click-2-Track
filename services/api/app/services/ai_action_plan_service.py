"""On-demand AI-generated action plans for service managers (Part F)."""
import json
import os
from datetime import datetime, timedelta
from typing import Optional

import httpx

from app.core.config import settings


class _AIActionPlanService:
    """Build a natural-language action plan from workshop analytics.

    On-demand only: backend is called only when the user presses 'Generate
    recommendation'. To control cost, a mock provider is used unless real
    credentials are configured. Output is always plain text for the service
    manager to review.
    """

    @staticmethod
    def _build_prompt(
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        branch_id: Optional[int] = None,
        vehicle_flow: Optional[dict] = None,
        deviation_summary: Optional[dict] = None,
        at_risk_alerts: Optional[list] = None,
        parts_shortage_patterns: Optional[dict] = None,
        staff_utilization: Optional[list] = None,
        rework_rate: Optional[dict] = None,
    ) -> str:
        return f"""You are a senior service manager advisor for an automotive workshop.
Generate a concise, actionable plan based on the following data for the period {period_start or '(latest available)'} to {period_end or '(latest available)'}.

Workshop context:
- branch_id: {branch_id or 'all branches'}

Vehicle flow summary:
{json.dumps(vehicle_flow or {}, indent=2, default=str)[:1200]}

Deviation summary:
{json.dumps(deviation_summary or {}, indent=2, default=str)[:800]}

At-risk vehicles currently exceeding target time:
{json.dumps(at_risk_alerts or [], indent=2, default=str)[:800]}

Parts shortage patterns:
{json.dumps(parts_shortage_patterns or {}, indent=2, default=str)[:800]}

Staff utilization snapshot:
{json.dumps(staff_utilization or [], indent=2, default=str)[:800]}

Rework rate snapshot:
{json.dumps(rework_rate or {}, indent=2, default=str)[:800]}

Please return:
1. The single biggest bottleneck and why.
2. Two or three concrete, prioritised actions the service manager should take tomorrow.
3. Who should own each action.
4. A one-sentence note on whether the situation appears normal or urgent.
Keep the response under 300 words and use bullet points.
"""

    @classmethod
    async def generate(
        cls,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        branch_id: Optional[int] = None,
        vehicle_flow: Optional[dict] = None,
        deviation_summary: Optional[dict] = None,
        at_risk_alerts: Optional[list] = None,
        parts_shortage_patterns: Optional[dict] = None,
        staff_utilization: Optional[list] = None,
        rework_rate: Optional[dict] = None,
    ) -> dict:
        prompt = cls._build_prompt(
            period_start=period_start,
            period_end=period_end,
            branch_id=branch_id,
            vehicle_flow=vehicle_flow,
            deviation_summary=deviation_summary,
            at_risk_alerts=at_risk_alerts,
            parts_shortage_patterns=parts_shortage_patterns,
            staff_utilization=staff_utilization,
            rework_rate=rework_rate,
        )

        provider = settings.AI_PROVIDER.lower().strip()

        if provider == "mock":
            return {
                "provider_used": "mock",
                "cost_note": "No API cost. Configure AI_PROVIDER + AI_API_KEY for a real LLM.",
                "action_plan": cls._mock_action_plan(vehicle_flow, at_risk_alerts, parts_shortage_patterns),
            }

        if provider in ("openai", "openrouter"):
            return await cls._call_openai_compatible(prompt, provider)

        raise NotImplementedError(f"AI provider '{provider}' is not implemented")

    @classmethod
    async def _call_openai_compatible(cls, prompt: str, provider: str) -> dict:
        api_key = settings.AI_API_KEY
        if not api_key:
            return {
                "provider_used": provider,
                "error": f"AI_API_KEY not configured for provider {provider}. Falling back to mock.",
                "action_plan": cls._mock_action_plan(None, None, None),
            }
        model = settings.AI_MODEL or ("openai/gpt-4o-mini" if provider == "openrouter" else "gpt-4o-mini")
        base_url = settings.AI_API_URL or ("https://openrouter.ai/api/v1" if provider == "openrouter" else "https://api.openai.com/v1")

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    **({"HTTP-Referer": "https://click2track.local", "X-Title": "Workshop Click-2-Track"} if provider == "openrouter" else {}),
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a concise automotive workshop operations advisor."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.5,
                    "max_tokens": 600,
                },
            )
        if resp.status_code != 200:
            return {
                "provider_used": provider,
                "error": f"LLM call failed: HTTP {resp.status_code} - {resp.text[:500]}",
                "action_plan": cls._mock_action_plan(None, None, None),
            }
        payload = resp.json()
        choice = payload.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content") or "(no response)"
        return {
            "provider_used": provider,
            "model": model,
            "raw_usage": payload.get("usage"),
            "action_plan": content,
        }

    @classmethod
    def _mock_action_plan(cls, vehicle_flow, at_risk_alerts, parts_shortage_patterns) -> str:
        bottleneck = "unknown bottleneck"
        if vehicle_flow and vehicle_flow.get("worst_bottleneck"):
            b = vehicle_flow["worst_bottleneck"]
            bottleneck = f"{b.get('stage_name') or b.get('stage_code')} (avg wait {b.get('avg_wait_minutes')} min)"

        risk_count = len(at_risk_alerts) if isinstance(at_risk_alerts, list) else 0
        top_parts = "None recorded"
        if parts_shortage_patterns and parts_shortage_patterns.get("top_patterns"):
            top_parts = ", ".join(p.get("pattern_key", "?") for p in parts_shortage_patterns["top_patterns"][:3])

        return (
            f"Mock AI action plan (configure AI_PROVIDER + AI_API_KEY for a real LLM).\n\n"
            f"Biggest bottleneck: {bottleneck}.\n"
            f"At-risk vehicles exceeding FRT target: {risk_count}.\n"
            f"Top parts shortage patterns: {top_parts}.\n\n"
            "Recommended actions:\n"
            "1. Review the bottleneck stage first thing tomorrow; confirm staffing and parts availability.\n"
            "2. Assign the at-risk vehicles to senior technicians and raise parts-wait flags early.\n"
            "3. Share the top parts-shortage patterns with the Parts Manager for inventory planning.\n\n"
            "Status: Needs manager review."
        )
