from pydantic import BaseModel, field_validator
from typing import Optional, Literal

HomeAway = Literal["home", "away", "any"]

class Filters(BaseModel):
    team: Optional[str] = None
    opponent: Optional[str] = None
    home_away: HomeAway = "any"
    competition: Optional[str] = None
    city: Optional[str] = None
    venue: Optional[str] = None
    date_from: Optional[str] = None  # YYYY-MM-DD
    date_to: Optional[str] = None
    weekday: Optional[Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]] = None
    time_gte: Optional[str] = None   # HH:MM
    time_lte: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    radius_km: Optional[int] = 30
    week: Optional[int] = None

    @field_validator("competition")
    @classmethod
    def whitelist_comp(cls, v):
        if not v: return v
        allow = {
            "Jupiler Pro League",
            "Lotto Super League", 
            "BNXT League 2025 - 2026",
            "LOTTO VOLLEY LEAGUE MEN",
            "BELGIAN VOLLEY LEAGUE WOMEN"
        }
        return v if v in allow else None

    @field_validator("radius_km")
    @classmethod
    def clamp_radius(cls, v):
        if v is None: return None
        return max(1, min(int(v), 100))

class QueryRequest(BaseModel):
    query: str
    user_location: Optional[dict] = None  # {"lat": 50.8503, "lon": 4.3517}

class QueryResponse(BaseModel):
    filters: Filters
    sql_query: Optional[str] = None
    results: Optional[list] = None
    explanation: Optional[str] = None
