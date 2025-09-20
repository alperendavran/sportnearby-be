#!/usr/bin/env python3
# -*- coding: utf-8-sig -*-
"""
FastAPI REST API for Sports Events
SOLID prensiplerine uygun yakınlık tabanlı etkinlik API'si
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import psycopg
from psycopg.rows import dict_row
from datetime import datetime, timedelta
import os
import subprocess
import json
import requests

# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "sports_events",
    "user": "alperendavran",
    "password": None  # macOS PostgreSQL default
}

# Utility functions
def to_pg_dow_list(weekday: Optional[List[str]]) -> Optional[List[int]]:
    """Python weekday list to PostgreSQL DOW array"""
    if not weekday:
        return None
    # PG: Sun=0..Sat=6
    pg_map = {"Mon":1,"Tue":2,"Wed":3,"Thu":4,"Fri":5,"Sat":6,"Sun":0}
    out = []
    for w in weekday:
        w = w.strip().title()  # mon->Mon
        if w in pg_map:
            out.append(pg_map[w])
    return out or None

def normalize_dates(date_from: Optional[str], date_to: Optional[str]):
    """Validate and normalize date strings"""
    def is_date(s): 
        try:
            datetime.strptime(s, "%Y-%m-%d"); return True
        except: return False
    return (date_from if (date_from and is_date(date_from)) else None,
            date_to   if (date_to   and is_date(date_to))   else None)

# Pydantic models (Data Transfer Objects)
class EventResponse(BaseModel):
    """Event response model - Interface Segregation Principle"""
    id: int
    match_name: str
    competition: Optional[str]
    competition_group: Optional[str]
    venue: Optional[str]
    venue_city: Optional[str]
    datetime_local: datetime
    lat: float
    lon: float
    distance_m: Optional[float] = None

class NearbyRequest(BaseModel):
    """Nearby events request model"""
    lat: float
    lon: float
    radius_km: int = 30
    days: int = 7
    competition: Optional[str] = None
    limit: int = 200

class QueryRequest(BaseModel):
    """Natural language query request model"""
    query: str
    user_lat: Optional[float] = None
    user_lon: Optional[float] = None

class QueryResponse(BaseModel):
    """Natural language query response model"""
    query: str
    extracted_info: Dict[str, Any]
    sql_query: str
    explanation: str
    results: Optional[List[EventResponse]] = None

class DatabaseService:
    """Database işlemleri için Service Layer - Single Responsibility"""
    
    def __init__(self, config: dict):
        self.config = config
    
    def get_connection(self):
        """Database bağlantısı al"""
        return psycopg.connect(**self.config, row_factory=dict_row)
    
    
    def get_nearby_events_v2(
        self,
        *,
        lat: float,
        lon: float,
        radius_km: int = 30,
        date_from: Optional[str] = None,   # "YYYY-MM-DD" veya None
        date_to: Optional[str] = None,
        weekday_pg: Optional[List[int]] = None,  # PG DOW: Sun=0..Sat=6
        team: Optional[str] = None,
        opponent: Optional[str] = None,
        home_away: Optional[str] = None,   # "home" | "away" | None
        competition: Optional[str] = None,
        sort: str = "time",                # "time" | "distance"
        page: int = 1,
        page_size: int = 20,
        fields: Optional[List[str]] = None # seçmeli kolonlar
    ) -> Dict[str, Any]:
        """
        Gelişmiş yakın arama: competition, team/opponent, weekday (çoklu),
        home_away, sort (time|distance), pagination + total_count.
        """

        # Alan seçimi (güvenli beyaz liste)
        all_cols = {
            "id","match_name","competition","competition_group","venue","venue_city",
            "datetime_local","lat","lon"
        }
        select_cols = all_cols if not fields else set(fields) & all_cols
        if not select_cols:  # Eğer hiç kolon seçilmemişse default'ları kullan
            select_cols = all_cols
        select_sql = "e." + ", e.".join(sorted(select_cols))
        # distance ve total_count her zaman dönüyor
        select_sql += """, ST_Distance(e.geom, ST_SetSRID(ST_MakePoint($4,$3),4326)::geography) AS distance_m,
                          COUNT(*) OVER() AS total_count"""

        # tarih aralığı
        df_ts = None
        dt_ts = None
        if date_from:
            df_ts = f"{date_from} 00:00:00+02"  # Europe/Brussels varsayımı
        if date_to:
            dt_ts = f"{date_to} 23:59:59+02"

        radius_m = max(1, min(int(radius_km), 100)) * 1000
        limit = max(1, min(int(page_size), 100))
        offset = (max(1, page) - 1) * limit

        # Basit SQL - sadece temel sütunlar
        sql = """
        SELECT
          e.id, e.match_name, e.competition, e.venue, e.datetime_local, e.lat, e.lon,
          ST_Distance(e.geom, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography) AS distance_m
        FROM events e
        WHERE e.datetime_local >= (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels')
          AND e.datetime_local <  (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels') + INTERVAL '7 days'
          AND ST_DWithin(e.geom, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s)
        ORDER BY e.datetime_local ASC
        LIMIT %s;
        """

        params = (
            lon,                # %s 1
            lat,                # %s 2
            lon,                # %s 3
            lat,                # %s 4
            radius_m,           # %s 5
            limit,              # %s 6
        )

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

        # Competition filtresini Python'da uygula
        if competition:
            rows = [r for r in rows if r['competition'] == competition]

        return {
            "total": len(rows),
            "page": page,
            "page_size": limit,
            "results": rows
        }
    
    def get_competitions(self) -> List[str]:
        """Mevcut competition'ları getir"""
        sql = "SELECT DISTINCT competition FROM events WHERE competition IS NOT NULL ORDER BY competition;"
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    return [row['competition'] for row in cur.fetchall()]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    def get_venues(self) -> List[dict]:
        """Mevcut venue'ları getir"""
        sql = """
        SELECT DISTINCT venue, venue_city, lat, lon 
        FROM events 
        WHERE venue IS NOT NULL 
        ORDER BY venue;
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    return cur.fetchall()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

class NaturalLanguageProcessor:
    """Doğal dil işleme servisi - Single Responsibility"""
    
    def extract_with_ollama_http(self, query: str) -> Dict[str, Any]:
        """Ollama HTTP API ile bilgi çıkarımı (JSON garantisi)"""
        body = {
            "model": "llama3.1:8b-instruct",
            "format": "json",
            "messages": [
                {
                    "role": "system",
                    "content": """You are an information extractor. Extract filters from the user query.

Return ONLY valid JSON with this schema:
{
  "team": str|null,
  "competition": str|null,
  "weekday": "Mon"|"Tue"|"Wed"|"Thu"|"Fri"|"Sat"|"Sun"|null,
  "radius_km": int|null
}

Normalization rules:
- "weekend" => "Sat"
- Competitions: football/soccer -> "Jupiler Pro League"
               women football -> "Lotto Super League"
               basketball -> "BNXT League 2025 - 2026"
               volleyball -> "LOTTO VOLLEY LEAGUE MEN"
- If query mentions Brussels/Antwerp/Ghent or 'near me', radius_km defaults to 30.
- If unsure, use null."""
                },
                {
                    "role": "user",
                    "content": f"User query: {query}"
                }
            ],
            "options": {"temperature": 0}
        }
        
        try:
            r = requests.post("http://localhost:11434/api/chat", json=body, timeout=20)
            r.raise_for_status()
            # Ollama returns {"message":{"content":"{...json...}"}, ...}
            content = r.json()["message"]["content"]
            return json.loads(content)
        except Exception as e:
            print(f"Ollama HTTP error: {e}")
            return self.extract_with_regex(query)
    
    def extract_with_ollama(self, query: str) -> Dict[str, Any]:
        """Ollama ile bilgi çıkarımı (subprocess fallback)"""
        # Önce HTTP API'yi dene
        try:
            return self.extract_with_ollama_http(query)
        except:
            pass
            
        # Fallback: subprocess
        prompt = f"""
You are an information extractor. Extract filters from the user query.

Return ONLY valid JSON (no markdown, no code block, no extra text) with this schema:
{{
  "team": str|null,
  "competition": str|null,
  "weekday": "Mon"|"Tue"|"Wed"|"Thu"|"Fri"|"Sat"|"Sun"|null,
  "radius_km": int|null
}}

Normalization rules:
- "weekend" => "Sat"
- Competitions: football/soccer -> "Jupiler Pro League"
               women football -> "Lotto Super League"
               basketball -> "BNXT League 2025 - 2026"
               volleyball -> "LOTTO VOLLEY LEAGUE MEN"
- If query mentions Brussels/Antwerp/Ghent or 'near me', radius_km defaults to 30.
- If unsure, use null.

User query: "{query}"
JSON:
""".strip()
        
        try:
            result = subprocess.run(
                ['ollama', 'run', 'llama3.1:8b-instruct', prompt],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                # Çoğu zaman direkt JSON gelecek; yine de en dış {{ ... }} yakala
                start = output.find('{')
                end = output.rfind('}') + 1
                if start != -1 and end > 0:
                    return json.loads(output[start:end])
        except Exception as e:
            print(f"Ollama error: {e}")
        
        # Fallback to regex
        return self.extract_with_regex(query)
    
    def extract_with_regex(self, query: str) -> Dict[str, Any]:
        """Regex fallback extraction"""
        query_lower = query.lower()
        
        result = {
            "team": None,
            "competition": None,
            "weekday": None,
            "radius_km": None
        }
        
        # Team detection
        teams = ["genk", "anderlecht", "brugge", "antwerp", "gent", "leuven", "westerlo", "standard", "cercle", "oh leuven"]
        for team in teams:
            if team in query_lower:
                result["team"] = team.title()
                break
        
        # Competition detection
        if "women" in query_lower and ("football" in query_lower or "soccer" in query_lower):
            result["competition"] = "Lotto Super League"
        elif "basketball" in query_lower:
            result["competition"] = "BNXT League 2025 - 2026"
        elif "volleyball" in query_lower or "volley" in query_lower:
            result["competition"] = "LOTTO VOLLEY LEAGUE MEN"
        elif "football" in query_lower or "soccer" in query_lower or "maç" in query_lower:
            result["competition"] = "Jupiler Pro League"
        
        # Weekday detection
        if "weekend" in query_lower or "hafta sonu" in query_lower:
            result["weekday"] = "Sat"
        elif "monday" in query_lower or "pazartesi" in query_lower:
            result["weekday"] = "Mon"
        elif "tuesday" in query_lower or "salı" in query_lower:
            result["weekday"] = "Tue"
        elif "wednesday" in query_lower or "çarşamba" in query_lower:
            result["weekday"] = "Wed"
        elif "thursday" in query_lower or "perşembe" in query_lower:
            result["weekday"] = "Thu"
        elif "friday" in query_lower or "cuma" in query_lower:
            result["weekday"] = "Fri"
        elif "saturday" in query_lower or "cumartesi" in query_lower:
            result["weekday"] = "Sat"
        elif "sunday" in query_lower or "pazar" in query_lower:
            result["weekday"] = "Sun"
        
        # Location detection
        cities = ["brussels", "antwerp", "ghent", "bruges", "liege", "charleroi", "namur", "mons", "leuven"]
        if any(city in query_lower for city in cities) or "near me" in query_lower:
            result["radius_km"] = 30
        
        return result
    
    def generate_sql(self, extracted: Dict[str, Any]) -> str:
        """Extracted bilgilerden SQL oluştur"""
        sql_parts = ["SELECT * FROM events WHERE 1=1"]
        
        if extracted.get("team"):
            sql_parts.append(f"AND match_name ILIKE '{extracted['team']}'")
        
        if extracted.get("competition"):
            sql_parts.append(f"AND competition = '{extracted['competition']}'")
        
        if extracted.get("weekday"):
            if extracted["weekday"] == "Sat":
                sql_parts.append("AND EXTRACT(DOW FROM datetime_local) IN (6, 0)")
            else:
                dow_map = {"Mon": 1, "Tue": 2, "Wed": 3, "Thu": 4, "Fri": 5, "Sun": 0}
                if extracted["weekday"] in dow_map:
                    sql_parts.append(f"AND EXTRACT(DOW FROM datetime_local) = {dow_map[extracted['weekday']]}")
        
        if extracted.get("radius_km"):
            sql_parts.append(f"-- Location search within {extracted['radius_km']}km")
        
        sql_parts.append("ORDER BY datetime_local ASC LIMIT 10")
        return " ".join(sql_parts)
    
    def create_explanation(self, extracted: Dict[str, Any]) -> str:
        """Human-readable açıklama oluştur"""
        parts = []
        
        if extracted.get("team"):
            parts.append(f"Searching for {extracted['team']} matches")
        
        if extracted.get("competition"):
            parts.append(f"in {extracted['competition']}")
        
        if extracted.get("weekday"):
            parts.append(f"on {extracted['weekday']}")
        
        if extracted.get("radius_km"):
            parts.append(f"within {extracted['radius_km']}km radius")
        
        return " ".join(parts) if parts else "General sports events search"

# FastAPI app
app = FastAPI(
    title="Sports Events API",
    description="Yakınlık tabanlı spor etkinlikleri API'si",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency injection - Dependency Inversion Principle
db_service = DatabaseService(DB_CONFIG)
nlp_processor = NaturalLanguageProcessor()

@app.get("/")
async def root():
    """API ana sayfası"""
    return {
        "message": "Sports Events API",
        "version": "1.0.0",
        "endpoints": {
            "nearby": "/nearby - Yakındaki etkinlikleri getir",
            "query": "/query - Doğal dil ile etkinlik arama",
            "competitions": "/competitions - Mevcut ligleri listele",
            "venues": "/venues - Mevcut venue'ları listele",
            "health": "/health - API sağlık kontrolü"
        }
    }

@app.get("/nearby")
async def get_nearby_events(
    lat: float = Query(..., description="Kullanıcının enlemi"),
    lon: float = Query(..., description="Kullanıcının boylamı"),
    radius_km: int = Query(30, ge=1, le=100, description="Arama yarıçapı (km)"),
    competition: Optional[str] = Query(None, description="Lig filtresi")
):
    """
    Basit yakınlık tabanlı etkinlik arama
    """
    
    # Temel doğrulamalar
    if not (-90 <= lat <= 90):
        raise HTTPException(status_code=400, detail="Latitude must be between -90 and 90")
    if not (-180 <= lon <= 180):
        raise HTTPException(status_code=400, detail="Longitude must be between -180 and 180")

    data = db_service.get_nearby_events_v2(
        lat=lat, lon=lon, radius_km=radius_km, competition=competition
    )
    return data

@app.post("/query", response_model=QueryResponse)
async def process_natural_language_query(request: QueryRequest):
    """
    Doğal dil ile etkinlik arama
    
    - **query**: Doğal dil sorgusu (örn: "Genk maçları bu hafta sonu")
    - **user_lat**: Kullanıcının enlemi (opsiyonel, lokasyon bazlı aramalar için)
    - **user_lon**: Kullanıcının boylamı (opsiyonel, lokasyon bazlı aramalar için)
    """
    
    try:
        # Doğal dil işleme
        extracted = nlp_processor.extract_with_ollama(request.query)
        
        # Kullanıcı konumu varsa radius_km ekle
        if request.user_lat and request.user_lon and extracted.get("radius_km") is None:
            extracted["radius_km"] = 30
        
        # SQL oluştur
        sql_query = nlp_processor.generate_sql(extracted)
        
        # Açıklama oluştur
        explanation = nlp_processor.create_explanation(extracted)
        
        # Eğer kullanıcı konumu varsa ve radius_km varsa, gerçek sonuçları getir
        results = None
        if request.user_lat and request.user_lon and extracted.get("radius_km"):
            # Yeni v2 fonksiyonunu kullan
            data = db_service.get_nearby_events_v2(
                lat=request.user_lat,
                lon=request.user_lon,
                radius_km=extracted["radius_km"],
                competition=extracted.get("competition"),
                page=1,
                page_size=50
            )
            events = data["results"]
            
            # Team filtresi varsa uygula
            if extracted.get("team"):
                events = [e for e in events if extracted["team"].lower() in e["match_name"].lower()]
            
            # Weekday filtresi varsa uygula
            if extracted.get("weekday"):
                # PYTHON weekday(): Mon=0 ... Sun=6
                py_dow_map = {"Mon":0, "Tue":1, "Wed":2, "Thu":3, "Fri":4, "Sat":5, "Sun":6}
                wanted = extracted["weekday"]
                target_dow = py_dow_map.get(wanted)
                
                if target_dow is not None:
                    filtered_events = []
                    for event in events:
                        event_date = event["datetime_local"]
                        if isinstance(event_date, str):
                            event_date = datetime.fromisoformat(event_date.replace('Z', '+00:00'))
                        if event_date.weekday() == target_dow:
                            filtered_events.append(event)
                    events = filtered_events
            
            results = events[:10]  # İlk 10 sonucu al
        
        return QueryResponse(
            query=request.query,
            extracted_info=extracted,
            sql_query=sql_query,
            explanation=explanation,
            results=results
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query processing error: {str(e)}")

@app.get("/competitions")
async def get_competitions():
    """Mevcut ligleri listele"""
    competitions = db_service.get_competitions()
    return {
        "competitions": competitions,
        "count": len(competitions)
    }

@app.get("/venues")
async def get_venues():
    """Mevcut venue'ları listele"""
    venues = db_service.get_venues()
    return {
        "venues": venues,
        "count": len(venues)
    }

@app.get("/health")
async def health_check():
    """API sağlık kontrolü"""
    try:
        # Database bağlantısını test et
        with db_service.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM events;")
                count = cur.fetchone()['count']
        
        return {
            "status": "healthy",
            "database": "connected",
            "events_count": count,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
