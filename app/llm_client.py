#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ollama LLM client for various AI operations
"""

import json
import asyncio
import httpx
from typing import Optional, List
from datetime import datetime

from langsmith import Client
from langchain_ollama import OllamaLLM
from langsmith import traceable

from .settings import settings
from .models import GeocodeOut, IntentDecision, DateRangeOut, CityMention, ExtractOut, TZ


class OllamaClient:
    """Centralized Ollama client for all LLM operations"""
    
    def __init__(self):
        # LangSmith Client
        if settings.langsmith_tracing:
            self.langsmith_client = Client(
                api_key=settings.langsmith_api_key,
                api_url=settings.langsmith_endpoint
            )
            print(f"✅ LangSmith tracing active: {settings.langsmith_project}")
        else:
            self.langsmith_client = None
            print("⚠️ LangSmith tracing disabled")

        # Ollama LLM
        self.ollama_llm = OllamaLLM(
            model=settings.ollama_model,
            base_url=settings.ollama_host
        )

    @traceable(project_name=settings.langsmith_project)
    async def geocode(self, text: str, retries: int = 2, timeout_s: int = 25) -> GeocodeOut:
        """
        Request only JSON output from LLM:
        """
        system_prompt = (
        "You are a STRICT geocoding tool. Case-insensitive: the casing of the input "
        "does not matter. You MUST return ONLY a JSON object with these exact fields: "
        "{'lat': float|null, 'lon': float|null, 'confidence': int, 'status': 'OK'|'UNKNOWN'}. "
        "Rules: 1) If the place is in Belgium, return lat/lon with confidence 70-100. "
        "2) If the place is NOT in Belgium, return lat/lon with confidence 0-30. "
        "3) If you cannot find the place, return lat:null, lon:null, confidence:0, status:'UNKNOWN'. "
        "4) Return ONLY the JSON, no explanations. Examples: "
        "'Brussels' -> {'lat': 50.85, 'lon': 4.35, 'confidence': 100, 'status': 'OK'}, "
        "'Paris' -> {'lat': 48.85, 'lon': 2.35, 'confidence': 20, 'status': 'OK'}, "
        "'xyz123' -> {'lat': null, 'lon': null, 'confidence': 0, 'status': 'UNKNOWN'}"
        )

        user_prompt = f"Geocode this place in Belgium: {text}"

        payload = {
            "model": settings.ollama_model, "stream": False, "format": "json",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "options": {"temperature": 0.0, "num_predict": 64, "seed": 42}
        }

        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.post(f"{settings.ollama_host}/api/chat", json=payload, timeout=timeout_s)
                    r.raise_for_status()
                    obj = json.loads(r.json()["message"]["content"])
                    return GeocodeOut(
                        lat=obj.get("lat"),
                        lon=obj.get("lon"),
                        confidence=obj.get("confidence", 0),
                        status=obj.get("status", "UNKNOWN"),
                        source_text=text,
                        provider="ollama"
                    )
            except Exception as e:
                if attempt == retries:
                    return GeocodeOut(
                        lat=None, lon=None, confidence=0, status="UNKNOWN",
                        source_text=text, provider="ollama"
                    )
                await asyncio.sleep(1)

    @traceable(project_name=settings.langsmith_project)
    async def classify_intent(self, text: str) -> IntentDecision:
        system = (
          "You classify user requests about sports events in Belgium.\n"
          "Intent types:\n"
          "- 'list_competitions': User asks about available leagues/competitions (e.g., 'what competitions are there', 'show me all leagues')\n"
          "- 'events_near': User wants events near their location (e.g., 'events near me', 'nearby matches')\n"
          "- 'events_in_cities': User wants events in specific cities (e.g., 'Brussels sports events', 'Antwerp matches')\n"
          "- 'events_by_competition': User wants events for specific competitions (e.g., 'Pro League matches', 'Jupiler League')\n"
          "- 'events_by_venue': User wants events at specific venues (e.g., 'Lotto Park matches')\n"
          "- 'next_at_venue': User wants next event at a specific venue (e.g., 'next event at Lotto Park')\n"
          "- 'venues_near': User wants venues near their location (e.g., 'nearby stadiums')\n"
          "- 'events_by_timeframe': User wants events within a specific time period (e.g., 'Events within 8 weeks', 'matches in next month')\n"
          "- 'unclear_query': General questions, random text, gibberish, personal/romantic messages, or unclear requests that don't specify what the user wants\n"
          "IMPORTANT: If the text is too general (like 'what can I do', 'sports activities'), contains random characters, numbers, personal messages (like 'I love you', 'seni seviyorum'), or doesn't specify a clear intent, classify as 'unclear_query'.\n"
          "Return JSON: {'intent': 'intent_name', 'slots': {'cities': [], 'competitions': [], 'venues': [], 'radius_km': null}}"
        )

        user = f"Classify this request: {text}"

        payload = {
            "model": settings.ollama_model, "stream": False, "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "options": {"temperature": 0.0, "num_predict": 128, "seed": 42}
        }

        async with httpx.AsyncClient() as client:
            r = await client.post(f"{settings.ollama_host}/api/chat", json=payload, timeout=20)
            r.raise_for_status()
            obj = json.loads(r.json()["message"]["content"])
            # Ensure slots field is present
            if "slots" not in obj:
                obj["slots"] = {}
            return IntentDecision(**obj)

    @traceable(project_name=settings.langsmith_project)
    async def resolve_date_range(self, text: str, now_dt: Optional[datetime]=None) -> DateRangeOut:
        """Let LLM do the date calculation; we only do JSON parsing + sanity check."""
        now = now_dt or datetime.now(TZ)
        current_date = now.date().isoformat()
        current_dow = now.strftime("%A")  # e.g., Thursday

        system = (
            "You are a date range normalizer for sports queries in Belgium.\n"
            "Given CURRENT_DATE (Europe/Brussels) and a user text, output ONLY JSON with:\n"
            "{ 'status':'OK'|'UNCLEAR'|'NO_TIME',"
            "  'time_keyword':'today'|'tonight'|'tomorrow'|'this_weekend'|'next_weekend'|'this_week'|'next_week'|'weeks_ahead'|'next_year'|'soon'|'later'|null,"
            "  'date_from':'YYYY-MM-DD'|null, 'date_to':'YYYY-MM-DD'|null, 'confidence':0-100 }\n"
            "Rules:\n"
            "- Base ALL calculations strictly on CURRENT_DATE.\n"
            "- 'this_weekend' = upcoming Saturday and Sunday relative to CURRENT_DATE; "
            "  'next_weekend' = the weekend after that.\n"
            "- 'this_week' = Monday..Sunday containing CURRENT_DATE; 'next_week' = the following week.\n"
            "- 'weeks_ahead' = multiple weeks from CURRENT_DATE (e.g., '8 weeks within' = 8 weeks from today).\n"
            "- 'next_year' = next calendar year (e.g., 'next year' = January 1 to December 31 of next year).\n"
            "- 'tonight' = CURRENT_DATE (date level; do not output time).\n"
            "- 'tomorrow' = CURRENT_DATE + 1 day; set BOTH date_from AND date_to to the same date.\n"
            "- For 'X weeks within' or 'X weeks ahead': date_from = CURRENT_DATE, date_to = CURRENT_DATE + X weeks.\n"
            "- For 'next year': date_from = January 1 of next year, date_to = December 31 of next year.\n"
            "  Example: If CURRENT_DATE is 2025-09-26, then 'next year' = date_from:'2026-01-01', date_to:'2026-12-31'.\n"
            "- Use ISO dates only; do not include times.\n"
            "- Prefer CURRENT_DATE.year unless the text explicitly mentions another month/year.\n"
            "- If NO time-related words are mentioned, return status='NO_TIME' with null dates.\n"
            "- If time-related words are mentioned but ambiguous (like 'soon', 'later', 'eventually', 'sometime'), return status='UNCLEAR' with time_keyword='soon' or 'later' and null dates.\n"
            "- If time-related words are clear, return status='OK' with proper dates.\n"
            "- IMPORTANT: For ambiguous terms like 'soon', 'later', 'eventually', 'sometime', 'in the future' - mark as UNCLEAR, don't try to guess specific dates.\n"
            "- CRITICAL: Only use 'next_year' time_keyword when the user explicitly mentions 'next year' or similar phrases. Do NOT use it for general queries without time context.\n"
        )

        user = (
            f"CURRENT_DATE: {current_date} ({current_dow}) TZ=Europe/Brussels\n"
            f"TEXT: {text}\n"
            "Examples:\n"
            "- 'next year' → status:'OK', time_keyword:'next_year', date_from:'2026-01-01', date_to:'2026-12-31'\n"
            "- 'this weekend' → status:'OK', time_keyword:'this_weekend', date_from:'2025-09-27', date_to:'2025-09-28'\n"
            "- 'tomorrow' → status:'OK', time_keyword:'tomorrow', date_from:'2025-09-27', date_to:'2025-09-27'\n"
            "- 'sports events' → status:'NO_TIME', time_keyword:null, date_from:null, date_to:null\n"
            "Return ONLY JSON."
        )

        payload = {
            "model": settings.ollama_model, "stream": False, "format": "json",
            "messages": [
                {"role":"system","content": system},
                {"role":"user","content": user}
            ],
            "options": {"temperature": 0.0, "num_predict": 256, "seed": 42}
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{settings.ollama_host}/api/chat", json=payload, timeout=20)
            r.raise_for_status()
            obj = json.loads(r.json()["message"]["content"])

        # --- light sanity check (not calculation, just validation) ---
        out = DateRangeOut(**obj)
        if out.status == "OK" and out.date_from and out.date_to:
            try:
                df = datetime.fromisoformat(out.date_from).date()
                dt_ = datetime.fromisoformat(out.date_to).date()
                today = now.date()
                # 1) date_from <= date_to
                if df > dt_:
                    out.status, out.date_from, out.date_to = "UNCLEAR", None, None
                # 2) year deviation (±500 days limit - sufficient for next year)
                elif abs((df - today).days) > 500 or abs((dt_ - today).days) > 500:
                    out.status, out.date_from, out.date_to = "UNCLEAR", None, None
            except Exception:
                out.status, out.date_from, out.date_to = "UNCLEAR", None, None
        return out

    async def extract_cities(self, text: str) -> ExtractOut:
        system = (
            "You extract city/municipality names from text. Return ONLY JSON: "
            "{'mentions': [{'text': 'original', 'normalized': 'cleaned', 'type': 'city'|'municipality'|'region', 'confidence': 0-100}]}"
        )
        user = f"Extract cities from: {text}"

        payload = {
            "model": settings.ollama_model, "stream": False, "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "options": {"temperature": 0.0, "num_predict": 128, "seed": 42}
        }

        async with httpx.AsyncClient() as client:
            r = await client.post(f"{settings.ollama_host}/api/chat", json=payload, timeout=20)
            r.raise_for_status()
            obj = json.loads(r.json()["message"]["content"])

        mentions = [CityMention(**item) for item in obj.get("mentions", [])]
        chosen = mentions[0] if mentions else None
        return ExtractOut(mentions=mentions, chosen=chosen)


# Global client instance
ollama_client = OllamaClient()
