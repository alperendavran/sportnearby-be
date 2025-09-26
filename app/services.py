#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Business logic and service layer
"""

import re
from typing import List, Optional, Tuple
from datetime import datetime
from fastapi import HTTPException

from .models import (
    GeocodeOut, IntentDecision, DateRangeOut, ExtractOut, MatchOut, 
    CityGeocodeItem, PipelineGeocodeOut, TZ
)
from .llm_client import ollama_client
from .db import (
    find_events_near_db, next_events_at_venue_db, venues_near_db,
    list_competitions_db, competition_ids_by_names, venue_ids_by_names
)


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in kilometers"""
    R = 6371  # Earth's radius in kilometers
    
    lat1_rad = lat1 * 3.14159265359 / 180
    lon1_rad = lon1 * 3.14159265359 / 180
    lat2_rad = lat2 * 3.14159265359 / 180
    lon2_rad = lon2 * 3.14159265359 / 180
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = (1 - (dlat / 2).__cos__()) + lat1_rad.__cos__() * lat2_rad.__cos__() * (1 - (dlon / 2).__cos__())
    c = 2 * (a.__sqrt__().__asin__())
    
    return R * c


def normalize_query(s: str) -> str:
    """Normalize query string"""
    return re.sub(r'[/_]+', ' ', s).strip()


def dedupe_keep_order(items: List[str]) -> List[str]:
    """Remove duplicates while preserving order"""
    seen = set()
    out = []
    for x in items:
        k = x.casefold()
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def in_belgium_bbox(lat: float, lon: float) -> bool:
    """Check if coordinates are within Belgium bounding box"""
    return 49.5 <= lat <= 51.6 and 2.5 <= lon <= 6.5


def resolve_radius(slots) -> float:
    """Resolve radius from slots or return default"""
    return slots.radius_km or 25.0


async def geocode_service(text: str) -> GeocodeOut:
    """Geocode a location using Ollama"""
    return await ollama_client.geocode(text)


async def extract_cities_service(text: str) -> ExtractOut:
    """Extract cities from text using Ollama"""
    return await ollama_client.extract_cities(text)


async def batch_geocode_city_names(
    names: List[str], 
    context: Optional[str] = "Belgium", 
    min_conf: int = 70, 
    bbox: bool = True
) -> List[CityGeocodeItem]:
    """Batch geocode multiple city names"""
    results: List[CityGeocodeItem] = []
    
    for name in dedupe_keep_order([n for n in names if n and n.strip()]):
        q = f"{name}, {context}" if context else name
        geo = await ollama_client.geocode(q)
        
        item = CityGeocodeItem(
            name=name, 
            lat=None, 
            lon=None, 
            status="UNKNOWN", 
            confidence=int(getattr(geo, "confidence", 0))
        )
        
        if (geo.status == "OK" and geo.lat is not None and geo.lon is not None and 
            (not bbox or in_belgium_bbox(geo.lat, geo.lon)) and 
            item.confidence >= min_conf):
            item.lat = float(geo.lat)
            item.lon = float(geo.lon)
            item.status = "OK"
        
        results.append(item)
    
    return results


async def pipeline_geocode_cities_service(cities_text: str) -> PipelineGeocodeOut:
    """Pipeline to extract and geocode multiple cities"""
    # Extract cities from text
    extract_result = await ollama_client.extract_cities(cities_text)
    city_names = [mention.normalized for mention in extract_result.mentions if mention.type in ["city", "municipality"]]
    
    if not city_names:
        return PipelineGeocodeOut(items=[], total=0, successful=0, failed=0)
    
    # Batch geocode
    items = await batch_geocode_city_names(city_names)
    
    successful = sum(1 for item in items if item.status == "OK")
    failed = len(items) - successful
    
    return PipelineGeocodeOut(
        items=items,
        total=len(items),
        successful=successful,
        failed=failed
    )


async def nearest_matches_service(
    lat: float,
    lon: float,
    radius_km: float = 25.0,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    competition_ids: Optional[List[int]] = None,
    venue_ids: Optional[List[int]] = None,
    limit: int = 20
) -> List[MatchOut]:
    """Find nearest matches with filters"""
    return await find_events_near_db(
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        date_from=date_from,
        date_to=date_to,
        competition_ids=competition_ids,
        venue_ids=venue_ids,
        limit=limit
    )


async def agent_query_service(
    q: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    limit: int = 20
) -> dict:
    """Main agent query service - orchestrates intent classification, slot resolution, and search"""
    
    # Intent classification
    decision = await ollama_client.classify_intent(q)
    slots = decision.slots
    
    # Handle intents that don't need date resolution
    if decision.intent == "list_competitions":
        competitions = await list_competitions_db()
        return {
            "intent": decision.intent,
            "query": q,
            "items": competitions
        }
    
    # Date resolution for location-dependent intents
    dr = await ollama_client.resolve_date_range(q)
    
    # NO_TIME durumunda bugünün tarihini kullan (varsayılan)
    if dr.status == "NO_TIME":
        today = datetime.now(TZ).date().isoformat()
        date_from, date_to = today, today
    else:
        date_from, date_to = (dr.date_from, dr.date_to) if dr.status == "OK" else (None, None)
    
    radius_km = resolve_radius(slots)
    
    # Only ask for clarification in unclear date situations
    if dr.status == "UNCLEAR" or (dr.status == "OK" and (date_from is None or date_to is None)):
        raise HTTPException(
            status_code=422, 
            detail={
                "message": "Date expression is unclear, please specify a clearer date.",
                "suggestion": "Examples: 'this weekend', 'tomorrow', 'next week', 'within 8 weeks'",
                "query": q,
                "date_resolution": {
                    "status": dr.status,
                    "time_keyword": dr.time_keyword,
                    "date_from": date_from,
                    "date_to": date_to,
                    "confidence": dr.confidence
                }
            }
        )

    # Coordinate resolver
    async def resolve_coords_from_text_or_cities() -> List[Tuple[float, float]]:
        if lat is not None and lon is not None:
            return [(lat, lon)]
        
        # Try to extract cities and geocode them
        extract_result = await ollama_client.extract_cities(q)
        if extract_result.mentions:
            city_names = [mention.normalized for mention in extract_result.mentions if mention.type in ["city", "municipality"]]
            if city_names:
                geocode_items = await batch_geocode_city_names(city_names)
                coords_list = [(item.lat, item.lon) for item in geocode_items if item.status == "OK" and item.lat and item.lon]
                if coords_list:
                    return coords_list
        
        # Fallback: try to geocode the entire query
        geo = await ollama_client.geocode(q)
        if geo.status == "OK" and geo.lat and geo.lon:
            return [(geo.lat, geo.lon)]
        
        # No location found - ask for clarification
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Location not specified. Please add a city name (e.g., 'Brussels sports activities') or share your coordinates.",
                "query": q,
                "suggestion": "Examples: 'Brussels sports activities', 'Antwerp matches', 'events near me'"
            }
        )

    # Handle different intents
    if decision.intent == "general_inquiry":
        return {
            "intent": decision.intent,
            "query": q,
            "message": "Please ask a more specific question about sports events.",
            "suggestions": [
                "What leagues are available?",
                "Brussels sports events",
                "Matches near me",
                "What's happening this weekend?"
            ]
        }
    
    else:
        # Location-dependent intents
        coords_list = await resolve_coords_from_text_or_cities()
        
        # Resolve competition and venue IDs
        competition_ids = await competition_ids_by_names(slots.competitions) if slots.competitions else None
        venue_ids = await venue_ids_by_names(slots.venues) if slots.venues else None
        
        # Search for events
        all_events = []
        for coord_lat, coord_lon in coords_list:
            events = await find_events_near_db(
                lat=coord_lat,
                lon=coord_lon,
                radius_km=radius_km,
                date_from=date_from,
                date_to=date_to,
                competition_ids=competition_ids,
                venue_ids=venue_ids,
                limit=limit
            )
            all_events.extend(events)
        
        # Remove duplicates and sort by distance
        seen_ids = set()
        unique_events = []
        for event in all_events:
            if event.id not in seen_ids:
                seen_ids.add(event.id)
                unique_events.append(event)
        
        unique_events.sort(key=lambda x: x.distance_km)
        unique_events = unique_events[:limit]
        
        return {
            "intent": decision.intent,
            "query": q,
            "count": len(unique_events),
            "events": unique_events,
            "filters": {
                "cities": slots.cities,
                "competitions": slots.competitions,
                "radius_km": radius_km,
                "date_from": date_from,
                "date_to": date_to
            },
            "date_resolution": {
                "status": dr.status,
                "time_keyword": dr.time_keyword,
                "confidence": dr.confidence
            }
        }
