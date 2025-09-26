#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pydantic models and data structures
"""

from typing import Optional, List, Literal
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Brussels")


class Point(BaseModel):
    lat: float
    lon: float


class GeocodeOut(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None
    confidence: int = 0
    status: str = "UNKNOWN"  # "OK" | "UNKNOWN"
    source_text: Optional[str] = None
    provider: str = "ollama"


class CityMention(BaseModel):
    text: str
    normalized: str
    type: Literal["city", "municipality", "region"]
    confidence: int = Field(ge=0, le=100)


class ExtractOut(BaseModel):
    mentions: List[CityMention]
    chosen: Optional[CityMention] = None


class MatchOut(BaseModel):
    id: int
    match_name: str
    datetime_local: str
    week: Optional[int] = None
    competition_id: int
    competition: str
    venue_id: int
    venue: str
    city: Optional[str] = None
    country: str
    latitude: float
    longitude: float
    geom: str
    distance_km: float


class DateRangeOut(BaseModel):
    status: Literal["OK","UNCLEAR","NO_TIME"]
    time_keyword: Optional[Literal[
        "today","tonight","tomorrow",
        "this_weekend","next_weekend",
        "this_week","next_week","weeks_ahead","next_year",
        "soon","later"
    ]] = None
    date_from: Optional[str] = None   # YYYY-MM-DD
    date_to: Optional[str] = None     # YYYY-MM-DD
    confidence: int = Field(ge=0, le=100, default=80)


class IntentSlots(BaseModel):
    cities: List[str] = []
    competitions: List[str] = []
    venues: List[str] = []
    radius_km: Optional[float] = None
    date_from: Optional[str] = None   # YYYY-MM-DD
    date_to: Optional[str] = None
    week: Optional[int] = None
    sort: Optional[Literal["distance","time"]] = "distance"


class Intent(str, Enum):
    events_near = "events_near"
    events_in_cities = "events_in_cities"
    events_by_competition = "events_by_competition"
    events_by_venue = "events_by_venue"
    next_at_venue = "next_at_venue"
    venues_near = "venues_near"
    list_competitions = "list_competitions"
    events_by_timeframe = "events_by_timeframe"
    unclear_query = "unclear_query"


class IntentDecision(BaseModel):
    intent: Intent
    slots: IntentSlots


class CityGeocodeItem(BaseModel):
    name: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    confidence: int = 0
    status: str = "UNKNOWN"  # "OK" | "UNKNOWN"


class PipelineGeocodeOut(BaseModel):
    items: List[CityGeocodeItem]
    total: int
    successful: int
    failed: int
