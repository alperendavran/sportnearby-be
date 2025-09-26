#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangChain Tools wrapper for existing services
"""

from typing import List, Optional, Dict, Any
from langchain_core.tools import tool

from .db import (
    find_events_near_db, next_events_at_venue_db, venues_near_db,
    competition_ids_by_names, venue_ids_by_names, list_competitions_db
)
from .llm_client import ollama_client


@tool("classify_intent")
async def classify_intent_tool(q: str) -> Dict[str, Any]:
    """Classify NL query into intent + slots."""
    dec = await ollama_client.classify_intent(q)
    return dec.model_dump()


@tool("normalize_dates")
async def normalize_dates_tool(q: str) -> Dict[str, Any]:
    """Normalize time expressions to [date_from, date_to]."""
    dr = await ollama_client.resolve_date_range(q)
    return dr.model_dump()


@tool("extract_cities")
async def extract_cities_tool(q: str) -> Dict[str, Any]:
    """Extract cities/municipalities from text."""
    ex = await ollama_client.extract_cities(q)
    return ex.model_dump()


@tool("geocode_text")
async def geocode_text_tool(q: str) -> Dict[str, Any]:
    """Geocode free text to lat/lon."""
    geo = await ollama_client.geocode(q)
    return geo.model_dump()


@tool("db_list_competitions")
async def db_list_competitions_tool(_q: str = "") -> List[Dict[str, Any]]:
    """List all available competitions."""
    return await list_competitions_db()


@tool("db_find_near")
async def db_find_near_tool(
    lat: float, 
    lon: float, 
    radius_km: float,
    date_from: Optional[str] = None, 
    date_to: Optional[str] = None,
    competition_ids: Optional[List[int]] = None, 
    venue_ids: Optional[List[int]] = None, 
    limit: int = 20, 
    sort: str = "distance"
) -> List[Dict[str, Any]]:
    """Find events near coordinates with filters."""
    rows = await find_events_near_db(
        lat, lon, radius_km, date_from, date_to, competition_ids, venue_ids, limit
    )
    # Pydantic objelerini dict'e çevir
    return [r.model_dump() for r in rows]


@tool("db_competition_ids")
async def db_competition_ids_tool(names: List[str]) -> List[int]:
    """Get competition IDs by names."""
    return await competition_ids_by_names(names or [])


@tool("db_venue_ids")
async def db_venue_ids_tool(names: List[str]) -> List[int]:
    """Get venue IDs by names."""
    return await venue_ids_by_names(names or [])


@tool("db_venues_near")
async def db_venues_near_tool(
    lat: float, 
    lon: float, 
    radius_km: float = 25.0, 
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Find venues near coordinates."""
    return await venues_near_db(lat, lon, radius_km, limit)


@tool("db_next_at_venue")
async def db_next_at_venue_tool(venue_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    """Get next events at a specific venue."""
    rows = await next_events_at_venue_db(venue_id, limit)
    return [r.model_dump() for r in rows]


# Tool listesi - graph'ta kullanmak için
TOOLS = [
    classify_intent_tool,
    normalize_dates_tool,
    extract_cities_tool,
    geocode_text_tool,
    db_list_competitions_tool,
    db_find_near_tool,
    db_competition_ids_tool,
    db_venue_ids_tool,
    db_venues_near_tool,
    db_next_at_venue_tool,
]
