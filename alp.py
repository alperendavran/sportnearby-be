import os
import re
import json
import time
from math import radians, sin, cos, sqrt, atan2
from typing import Optional, List, Literal
from datetime import datetime, date

import requests
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware

# =========================
# Config
# =========================
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

app = FastAPI(title="Geo Agent (Ollama-powered)", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
    allow_methods=["*"],
)



# =========================
# Demo match data (örnek)
# =========================
MATCHES = [
    {
        "id": "rscl-clubb", "home": "Standard Liège", "away": "Club Brugge",
        "city": "Liège", "stadium": "Stade Maurice Dufrasne",
        "lat": 50.6093, "lon": 5.5606,
        "kickoff": "2025-10-05T18:30:00+02:00"
    },
    {
        "id": "rsca-kvmech", "home": "RSC Anderlecht", "away": "KV Mechelen",
        "city": "Brussels", "stadium": "Lotto Park",
        "lat": 50.8387, "lon": 4.3228,
        "kickoff": "2025-10-03T20:45:00+02:00"
    },
    {
        "id": "antw-gent", "home": "Royal Antwerp", "away": "KAA Gent",
        "city": "Antwerpen", "stadium": "Bosuilstadion",
        "lat": 51.2369, "lon": 4.4661,
        "kickoff": "2025-10-12T16:00:00+02:00"
    },
    {
        "id": "usg-charl", "home": "Union SG", "away": "Charleroi",
        "city": "Forest/Vorst", "stadium": "Stade Joseph Marien",
        "lat": 50.8121, "lon": 4.3178,
        "kickoff": "2025-10-01T19:30:00+02:00"
    },
]

# =========================
# Models
# =========================
class Point(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)

class GeocodeOut(BaseModel):
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)
    confidence: int = Field(..., ge=0, le=100)
    status: str  # "OK" | "UNKNOWN"
    source_text: str
    provider: str = "ollama"

from typing import Dict
from enum import Enum
from zoneinfo import ZoneInfo
import psycopg2
from psycopg2.extras import RealDictCursor
import requests

# =========================
# Intent Classification System
# =========================
class Intent(str, Enum):
    events_near = "events_near"                 # lat/lon ile yakındaki etkinlikler
    events_in_cities = "events_in_cities"       # şehir(ler)den etkinlikler
    events_by_competition = "events_by_competition"
    events_by_venue = "events_by_venue"
    next_at_venue = "next_at_venue"
    venues_near = "venues_near"
    list_competitions = "list_competitions"

class DateRangeOut(BaseModel):
    status: Literal["OK","UNCLEAR"]
    time_keyword: Optional[Literal[
        "today","tonight","tomorrow",
        "this_weekend","next_weekend",
        "this_week","next_week"
    ]] = None
    date_from: Optional[str] = None   # YYYY-MM-DD
    date_to: Optional[str] = None     # YYYY-MM-DD
    confidence: int = Field(ge=0, le=100, default=80)

def resolve_date_range_via_llm(text: str, now_dt: Optional[datetime]=None) -> DateRangeOut:
    """Tarih hesaplamasını LLM yapsın; biz sadece JSON parse + sanity check yapalım."""
    now = now_dt or datetime.now(TZ)
    current_date = now.date().isoformat()
    current_dow = now.strftime("%A")  # e.g., Thursday

    system = (
        "You are a date range normalizer for sports queries in Belgium.\n"
        "Given CURRENT_DATE (Europe/Brussels) and a user text, output ONLY JSON with:\n"
        "{ 'status':'OK'|'UNCLEAR',"
        "  'time_keyword':'today'|'tonight'|'tomorrow'|'this_weekend'|'next_weekend'|'this_week'|'next_week'|null,"
        "  'date_from':'YYYY-MM-DD'|null, 'date_to':'YYYY-MM-DD'|null, 'confidence':0-100 }\n"
        "Rules:\n"
        "- Base ALL calculations strictly on CURRENT_DATE.\n"
        "- 'this_weekend' = upcoming Saturday and Sunday relative to CURRENT_DATE; "
        "  'next_weekend' = the weekend after that.\n"
        "- 'this_week' = Monday..Sunday containing CURRENT_DATE; 'next_week' = the following week.\n"
        "- 'tonight' = CURRENT_DATE (date level; do not output time).\n"
        "- Use ISO dates only; do not include times.\n"
        "- Prefer CURRENT_DATE.year unless the text explicitly mentions another month/year.\n"
        "- If ambiguous, return status='UNCLEAR' and null dates.\n"
    )

    user = (
        f"CURRENT_DATE: {current_date} ({current_dow}) TZ=Europe/Brussels\n"
        f"TEXT: {text}\n"
        "Return ONLY JSON."
    )

    payload = {
        "model": "llama3.1:8b", "stream": False, "format": "json",
        "messages": [
            {"role":"system","content": system},
            {"role":"user","content": user}
        ],
        "options": {"temperature": 0.0, "num_predict": 128, "seed": 42}
    }
    r = requests.post("http://localhost:11434/api/chat", json=payload, timeout=20)
    r.raise_for_status()
    obj = json.loads(r.json()["message"]["content"])

    # --- hafif sanity check (hesap değil, kontrol) ---
    out = DateRangeOut(**obj)
    if out.status == "OK" and out.date_from and out.date_to:
        try:
            df = datetime.fromisoformat(out.date_from).date()
            dt_ = datetime.fromisoformat(out.date_to).date()
            today = now.date()
            # 1) date_from <= date_to
            if df > dt_:
                out.status, out.date_from, out.date_to = "UNCLEAR", None, None
            # 2) yıl sapması (±370 gün sınırı)
            elif abs((df - today).days) > 370 or abs((dt_ - today).days) > 370:
                out.status, out.date_from, out.date_to = "UNCLEAR", None, None
        except Exception:
            out.status, out.date_from, out.date_to = "UNCLEAR", None, None
    return out

class IntentSlots(BaseModel):
    cities: List[str] = []
    competitions: List[str] = []
    venues: List[str] = []
    radius_km: Optional[float] = None
    date_from: Optional[str] = None   # YYYY-MM-DD
    date_to: Optional[str] = None
    week: Optional[int] = None
    sort: Optional[Literal["distance","time"]] = "distance"

class IntentDecision(BaseModel):
    intent: Intent
    slots: IntentSlots

def classify_intent_via_ollama(text: str) -> IntentDecision:
    system = (
      "You classify user requests about sports events in Belgium.\n"
      "Intent types:\n"
      "- 'list_competitions': User asks about available leagues/competitions (e.g., 'hangi ligler var', 'what competitions are there')\n"
      "- 'events_near': User wants events near their location (e.g., 'yakınımdaki maçlar', 'events near me')\n"
      "- 'events_in_cities': User wants events in specific cities (e.g., 'Brussels maçları', 'events in Antwerp')\n"
      "- 'events_by_competition': User wants events from specific competitions (e.g., 'JPL maçları', 'Pro League matches')\n"
      "- 'events_by_venue': User wants events at specific venues (e.g., 'Lotto Park maçları')\n"
      "- 'next_at_venue': User wants next events at a specific venue (e.g., 'Lotto Park sıradaki maç')\n"
      "- 'venues_near': User wants venues near their location (e.g., 'yakınımdaki stadyumlar')\n"
      "Return ONLY JSON with schema:\n"
      "{ 'intent': 'events_near'|'events_in_cities'|'events_by_competition'|'events_by_venue'|'next_at_venue'|'venues_near'|'list_competitions',\n"
      "  'slots': { 'cities': [str], 'competitions':[str], 'venues':[str], 'radius_km': number|null,\n"
      "             'date_from': 'YYYY-MM-DD'|null, 'date_to': 'YYYY-MM-DD'|null,\n"
      "             'week': number|null, 'sort':'distance'|'time'|null } }"
    )
    payload = {
        "model": "llama3.1:8b", "stream": False, "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text}
        ],
        "options": {"temperature": 0.0, "num_predict": 128}
    }
    r = requests.post("http://localhost:11434/api/chat", json=payload, timeout=20)
    r.raise_for_status()
    obj = json.loads(r.json()["message"]["content"])
    return IntentDecision(
        intent=Intent(obj["intent"]),
        slots=IntentSlots(**obj["slots"])
    )

# =========================
# Slot Resolvers
# =========================
TZ = ZoneInfo("Europe/Brussels")

def resolve_date_range(slots: IntentSlots) -> tuple[Optional[str], Optional[str]]:
    """Tarih aralığını çöz"""
    if slots.date_from or slots.date_to:
        return slots.date_from, slots.date_to
    return None, None

def resolve_radius(slots: IntentSlots) -> float:
    """Yarıçapı çöz"""
    return float(slots.radius_km or 25.0)

def pg():
    """PostgreSQL bağlantısı"""
    return psycopg2.connect(host="localhost", user="alperendavran", dbname="sports_events")

def competition_ids_by_names(names: List[str]) -> List[int]:
    """Competition isimlerinden ID'leri getir"""
    if not names: 
        return []
    sql = "SELECT id FROM competitions WHERE LOWER(name) = ANY(%s)"
    vals = [n.lower() for n in names]
    with pg() as conn, conn.cursor() as cur:
        cur.execute(sql, (vals,))
        rows = cur.fetchall()
    return [r[0] for r in rows]

def venue_ids_by_names(names: List[str]) -> List[int]:
    """Venue isimlerinden ID'leri getir"""
    if not names: 
        return []
    ids = []
    with pg() as conn, conn.cursor() as cur:
        for n in names:
            cur.execute("SELECT id FROM venues WHERE name ILIKE %s LIMIT 3", (f"%{n}%",))
            ids += [r[0] for r in cur.fetchall()]
    return ids[:10]

# =========================
# Database Query Functions
# =========================
def find_events_near_db(lat, lon, radius_km=25.0, date_from=None, date_to=None,
                        competition_ids: Optional[List[int]]=None, limit=20, sort="distance"):
    """Koordinatlara yakın etkinlikleri bul"""
    sql = """
    WITH user_pt AS (
      SELECT ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography AS g
    ),
    events_geo AS (
      SELECT e.id, e.match_name, e.datetime_local, e.week,
             c.id AS competition_id, c.name AS competition,
             v.id AS venue_id, v.name AS venue, v.city, v.country,
             v.latitude, v.longitude, v.geom::geography AS vg
      FROM events e
      JOIN venues v ON v.id = e.venue_id
      JOIN competitions c ON c.id = e.competition_id
      WHERE e.datetime_local >= NOW()
        AND (%(date_from)s::date IS NULL OR e.datetime_local::date >= %(date_from)s::date)
        AND (%(date_to)s::date   IS NULL OR e.datetime_local::date <= %(date_to)s::date)
        AND (%(comp)s::int[] IS NULL OR e.competition_id = ANY(%(comp)s::int[]))
    )
    SELECT eg.*, ST_Distance(eg.vg, up.g)/1000.0 AS distance_km
    FROM events_geo eg, user_pt up
    WHERE ST_DWithin(eg.vg, up.g, %(radius_m)s)
    ORDER BY
      CASE WHEN %(sort)s = 'time' THEN eg.datetime_local END ASC,
      CASE WHEN %(sort)s = 'distance' THEN ST_Distance(eg.vg, up.g) END ASC
    LIMIT %(limit)s;
    """
    params = {
      "lat": lat, "lon": lon, "radius_m": radius_km*1000,
      "date_from": date_from, "date_to": date_to,
      "comp": competition_ids, "limit": limit, "sort": sort
    }
    with pg() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchall()

def next_events_at_venue_db(venue_id: int, limit: int = 5):
    """Venue'da sıradaki etkinlikleri getir"""
    sql = """
    SELECT e.*, v.name AS venue
    FROM events e
    JOIN venues v ON v.id = e.venue_id
    WHERE e.venue_id = %(vid)s
      AND e.datetime_local >= NOW()
    ORDER BY e.datetime_local
    LIMIT %(lim)s;
    """
    with pg() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, {"vid": venue_id, "lim": limit})
        return cur.fetchall()

def venues_near_db(lat, lon, radius_km=25.0, limit=20):
    """Koordinatlara yakın venue'leri getir"""
    sql = """
    WITH user_pt AS (
      SELECT ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography AS g
    )
    SELECT v.*, ST_Distance(v.geom::geography, up.g)/1000.0 AS distance_km
    FROM venues v, user_pt up
    WHERE ST_DWithin(v.geom::geography, up.g, %(r)s)
    ORDER BY distance_km
    LIMIT %(lim)s;
    """
    with pg() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, {"lon": lon, "lat": lat, "r": radius_km*1000, "lim": limit})
        return cur.fetchall()

class CityMention(BaseModel):
    text: str                  # orijinal geçtiği şekli
    normalized: str            # canonical (ör. "Bruxelles-Ville", "Anderlecht")
    type: str                  # "city" | "municipality"
    confidence: int = Field(..., ge=0, le=100)

class ExtractOut(BaseModel):
    mentions: List[CityMention]

class CityGeocodeItem(BaseModel):
    name: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    confidence: int = 0
    status: str = "UNKNOWN"  # "OK" | "UNKNOWN"

class MatchOut(BaseModel):
    id: str
    home: str
    away: str
    city: str
    stadium: str
    lat: float
    lon: float
    kickoff: str
    distance_km: float

# =========================
# Utils
# =========================
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def valid_coord(lat: float, lon: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lon <= 180

def in_belgium_bbox(lat: float, lon: float) -> bool:
    return 49.5 <= lat <= 51.6 and 2.5 <= lon <= 6.5

def normalize_query(s: str) -> str:
    return re.sub(r'[/_]+', ' ', s).strip()

def dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        k = x.casefold()
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out

# Basit JSON yakalayıcısı (LLM bazen metin ekleyebilir)
JSON_BLOCK_RE = re.compile(r'\{.*\}', re.DOTALL)

def extract_json_candidate(text: str) -> dict:
    m = JSON_BLOCK_RE.search(text)
    if not m:
        raise ValueError("JSON bulunamadı")
    raw = m.group(0)
    return json.loads(raw)

# =========================
# Batch Geocode
# =========================
def batch_geocode_city_names(names: List[str], context: Optional[str] = "Belgium",
                             min_conf: int = 70, bbox: bool = True) -> List[CityGeocodeItem]:
    results: List[CityGeocodeItem] = []
    for name in dedupe_keep_order([n for n in names if n and n.strip()]):
        q = f"{name}, {context}" if context else name
        geo = geocode_via_ollama(q)
        item = CityGeocodeItem(name=name, lat=None, lon=None, status="UNKNOWN", confidence=int(getattr(geo, "confidence", 0)))
        if (geo.status == "OK" and geo.lat is not None and geo.lon is not None
            and (not bbox or in_belgium_bbox(geo.lat, geo.lon)) and item.confidence >= min_conf):
            item.lat = float(geo.lat)
            item.lon = float(geo.lon)
            item.status = "OK"
        results.append(item)
    return results

# =========================
# Ollama City Extractor
# =========================
def extract_city_via_ollama(text: str, retries: int = 1, timeout_s: int = 20) -> List[CityMention]:
    system_prompt = (
        "You are a STRICT NER tool for geography in Belgium. "
        "Identify only city or municipality names present in the text. "
        "Return ONLY JSON (no prose) with schema:\n"
        '{ "mentions": [ { "text": string, "normalized": string, "type": "city"|"municipality", "confidence": number } ] }\n'
        "Rules:\n"
        "- If none found, return {\"mentions\": []}.\n"
        "- Case-insensitive. Preserve original 'text' as appears.\n"
        "- 'normalized' must be a canonical name (e.g., 'Bruxelles-Ville', 'Anderlecht', 'Liège').\n"
        "- Do NOT guess names not present in the input."
    )
    user_prompt = f"Extract Belgian city/municipality names from: {text}\nReturn ONLY JSON."

    url = f"{OLLAMA_HOST}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": "json",   # kritik: direkt JSON dönsün
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "options": {
            "temperature": 0.0,
            "num_predict": 128
        }
    }

    last_err = None
    for _ in range(retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=timeout_s)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")
            obj = json.loads(content)
            raw_mentions = obj.get("mentions", [])
            mentions: List[CityMention] = []
            for m in raw_mentions:
                try:
                    mentions.append(CityMention(
                        text=m.get("text",""),
                        normalized=m.get("normalized","") or m.get("text",""),
                        type=m.get("type","city"),
                        confidence=int(m.get("confidence", 0))
                    ))
                except Exception:
                    continue
            return mentions
        except Exception as e:
            last_err = e
            time.sleep(0.3)
    # LLM başarısızsa boş liste döndür
    return []


# =========================
# Ollama Geocoder
# =========================
def geocode_via_ollama(text: str, retries: int = 2, timeout_s: int = 25) -> GeocodeOut:
    """
    LLM'den yalnızca JSON çıktısı istenir:
    """
    system_prompt = (
    "You are a STRICT geocoding tool. Case-insensitive: the casing of the input "
    "Given a place description, output ONLY a JSON object with this EXACT schema:\n"
    '{ "lat": number|null, "lon": number|null, "confidence": number, "status": "OK"|"UNKNOWN" }\n'
    "Rules:\n"
    "- If you CANNOT confidently resolve to a SPECIFIC place, return lat=null, lon=null, confidence=0, status=\"UNKNOWN\".\n"
    "- Never guess. Never default to a capital or centroid.\n"
    "- Decimal WGS84 only. No degree symbols. No extra keys. No prose."
)
    user_prompt = f"""
    Resolve this place to coordinates (Belgium context allowed but do NOT guess):
    {text}/Belgium

    Return ONLY JSON. Examples:
    Input: "asdfgqwerty" -> {{ "lat": null, "lon": null, "confidence": 0, "status": "UNKNOWN" }}
    Input: "Anderlecht"  -> {{ "lat": 50.84, "lon": 4.34, "confidence": 90, "status": "OK" }}
    """

    url = f"{OLLAMA_HOST}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        # İstersen sıcaklık düşür:
        "options": {"temperature": 0.0}
    }

    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=timeout_s)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")
            if not content:
                raise ValueError("Ollama boş yanıt döndürdü")

            try:
                obj = json.loads(content) if content.strip().startswith("{") else extract_json_candidate(content)
            except json.JSONDecodeError:
                # İçinden JSON bloğunu çıkar
                obj = extract_json_candidate(content)
            print(obj)
            
            lat = obj.get("lat")
            lon = obj.get("lon")
            confidence = int(obj.get("confidence", 0))
            status = str(obj.get("status", "UNKNOWN"))  

            if status != "OK" or confidence < 40 or lat is None or lon is None:
                return GeocodeOut(lat=None, lon=None, confidence=confidence, status="UNKNOWN", source_text=text)
            if not valid_coord(float(lat), float(lon)):
                return GeocodeOut(lat=None, lon=None, confidence=0, status="UNKNOWN", source_text=text)

                
            return GeocodeOut(lat=float(lat), lon=float(lon), confidence=confidence, status="OK", source_text=text)
        except Exception as e:
            last_err = e
            # kısa backoff
            time.sleep(0.4)

    raise HTTPException(status_code=502, detail=f"Ollama geocode hatası: {last_err}")

# =========================
# Endpoints
# =========================
@app.get("/health")
def health():
    return {"ok": True, "service": "Geo Agent (Ollama)"}

@app.get("/geocode", response_model=GeocodeOut)
def geocode(q: str = Query(...)):
    """
    Metinden koordinat: communes listesi KULLANMADAN, yalnızca Ollama.
    """
    return geocode_via_ollama(q)

@app.get("/extract-city", response_model=List[str])
def extract_city(q: str = Query(...)):
    """
    Metinden şehir/ilçe adını çıkar. Şehir ve belediye adlarını liste olarak döndürür.
    """
    mentions = extract_city_via_ollama(q)
    if mentions:
        return [x.normalized for x in mentions if x is not None]
    return []

@app.get("/nearest-matches", response_model=List[MatchOut])
def nearest_matches(
    lat: float, lon: float,
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    within_km: Optional[float] = Query(None, ge=0.0),
    limit: int = Query(10, ge=1, le=100),
):
    results: List[MatchOut] = []
    for m in MATCHES:
        kdt = datetime.fromisoformat(m["kickoff"])
        if date_from and kdt.date() < date_from:
            continue
        if date_to and kdt.date() > date_to:
            continue
        d = haversine(lat, lon, m["lat"], m["lon"])
        if within_km is not None and d > within_km:
            continue
        results.append(MatchOut(
            id=m["id"],
            home=m["home"],
            away=m["away"],
            city=m["city"],
            stadium=m["stadium"],
            lat=m["lat"], lon=m["lon"],
            kickoff=m["kickoff"],
            distance_km=round(d, 3),
        ))
    results.sort(key=lambda x: x.distance_km)
    return results[:limit]

@app.get("/nearest-matches-by-text", response_model=List[MatchOut])
def nearest_matches_by_text(
    q: str = Query(...),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    within_km: Optional[float] = Query(None, ge=0.0),
    limit: int = Query(10, ge=1, le=100),
):
    """
    Metinden konumu Ollama ile çözer, sonra yakın maçları verir.
    """
    geo = geocode_via_ollama(q)
    return nearest_matches(lat=geo.lat, lon=geo.lon, date_from=date_from, date_to=date_to, within_km=within_km, limit=limit)

@app.get("/pipeline/geocode-cities", response_model=List[CityGeocodeItem])
def pipeline_geocode_cities(
    text: Optional[str] = Query(None, description="Serbest metin: 'antwerp brüsel ve ghent'in koordinatlarını ver'"),
    names: Optional[str] = Query(None, description="Virgülle ayrık liste: 'Antwerpen, Brussels, Gent'"),
    context: Optional[str] = Query("Belgium"),
    min_conf: int = Query(70, ge=0, le=100),
):
    """
    - text verilirse: NER ile şehir/belediye adlarını çıkarır (hepsini).
    - names verilirse: 'Antwerpen, Brussels, Gent' gibi manuel listeyi işler.
    - Sonra her birini LLM ile geocode eder; hepsini döndürür (başarısız olanları da UNKNOWN olarak listeler).
    """
    city_names: List[str] = []

    if text:
        t = normalize_query(text)
        mentions = extract_city_via_ollama(t)  # <- senin NER fonksiyonun (CityMention listesi dönüyorsa)
        if isinstance(mentions, list) and mentions and hasattr(mentions[0], "normalized"):
            city_names = [m.normalized for m in mentions if getattr(m, "normalized", None)]
        else:
            # Eğer /extract-city endpoint'ini List[str] dönecek şekilde yazdıysan:
            # city_names = mentions
            pass

    if names:
        # "Antwerpen, Brussels ve Gent" gibi ifadeleri parçala
        parts = re.split(r",|\band\b|\bve\b|&|\n", names, flags=re.IGNORECASE)
        city_names += [normalize_query(p) for p in parts]

    if not city_names:
        raise HTTPException(status_code=422, detail={"message": "No city/municipality names found", "text": text, "names": names})

    return batch_geocode_city_names(city_names, context=context, min_conf=min_conf, bbox=True)

# =========================
# AI Agent Orchestrator
# =========================
@app.get("/agent/query")
def agent_query(
    q: str = Query(..., description="Doğal dil istek"),
    lat: Optional[float] = Query(None), 
    lon: Optional[float] = Query(None),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Doğal dil ile spor etkinlikleri sorgulama.
    
    Örnekler:
    - "Yarın yakınımdaki JPL maçları" (lat/lon ile)
    - "Brussels ve Antwerpen'de hafta sonu maçlar"
    - "Lotto Park'ta sıradaki 3 maç"
    - "Yakınımdaki stadyumlar"
    - "Hangi ligler var?"
    """
    try:
        # Intent classification
        decision = classify_intent_via_ollama(q)
        slots = decision.slots
        
        # Slot resolution - LLM ile tarih çözümleme
        dr = resolve_date_range_via_llm(q)
        date_from, date_to = (dr.date_from, dr.date_to) if dr.status == "OK" else (None, None)
        radius_km = resolve_radius(slots)
        
        # Belirsiz tarih durumunda kullanıcıya yönlendirme
        if dr.status == "UNCLEAR" and any(keyword in q.lower() for keyword in ["geçen", "önceki", "2023", "2024", "yıl"]):
            raise HTTPException(
                status_code=422, 
                detail={
                    "message": "Belirsiz tarih ifadesi, lütfen tarih aralığını netleştirir misin?",
                    "suggestion": "Örnek: 'bu hafta sonu', 'yarın', 'gelecek hafta'",
                    "query": q,
                    "date_resolution": {
                        "status": dr.status,
                        "time_keyword": dr.time_keyword,
                        "confidence": dr.confidence
                    }
                }
            )

        # Coordinate resolver
        def resolve_coords_from_text_or_cities() -> list[tuple[float,float]]:
            if lat is not None and lon is not None:
                return [(lat, lon)]
            coords = []
            # Çoklu şehir varsa hepsini tara
            if slots.cities:
                city_text = ",".join(slots.cities)
                mentions = extract_city_via_ollama(city_text)
                if mentions:
                    city_names = [m.normalized for m in mentions if m.normalized]
                    items = batch_geocode_city_names(city_names, context="Belgium", min_conf=70, bbox=True)
                    coords += [(it.lat, it.lon) for it in items if it.status=="OK" and it.lat and it.lon]
            if not coords:
                g = geocode_via_ollama(q)
                if g.status == "OK" and g.lat and g.lon:
                    coords.append((g.lat, g.lon))
            return coords

        # Intent handling
        if decision.intent == Intent.list_competitions:
            with pg() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, name, season, country FROM competitions ORDER BY name;")
                competitions = cur.fetchall()
                return {
                    "intent": decision.intent, 
                    "query": q,
                    "items": competitions
                }

        if decision.intent in (Intent.events_near, Intent.events_in_cities, Intent.events_by_competition):
            coords_list = resolve_coords_from_text_or_cities()
            if not coords_list:
                raise HTTPException(status_code=422, detail={"message":"Konum bulunamadı", "query": q})
            
            comp_ids = competition_ids_by_names(slots.competitions)
            all_rows = []
            
            for (la, lo) in coords_list:
                rows = find_events_near_db(
                    la, lo, radius_km=radius_km,
                    date_from=date_from, date_to=date_to,
                    competition_ids=comp_ids or None,
                    limit=limit, sort=slots.sort or "distance"
                )
                all_rows += rows
            
            # Aynı event id varsa en yakını tut
            best = {}
            for r in all_rows:
                rid = r["id"]
                if rid not in best or r["distance_km"] < best[rid]["distance_km"]:
                    best[rid] = r
            
            out = sorted(best.values(), key=lambda x: (x["datetime_local"] if (slots.sort=="time") else x["distance_km"]))
            
            return {
                "intent": decision.intent, 
                "query": q,
                "count": len(out), 
                "events": out[:limit],
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

        if decision.intent in (Intent.events_by_venue, Intent.next_at_venue):
            vids = venue_ids_by_names(slots.venues)
            if not vids:
                raise HTTPException(status_code=422, detail={"message":"Venue bulunamadı", "venues": slots.venues, "query": q})
            
            if decision.intent == Intent.events_by_venue:
                # Tüm venue'lar için sıradaki etkinlikleri getir
                out = []
                for vid in vids[:5]:
                    out += next_events_at_venue_db(vid, limit=min(5, limit))
                return {
                    "intent": decision.intent, 
                    "query": q,
                    "events": out[:limit]
                }
            else:
                # Tek venue'nun sıradaki N etkinliği (ilk eşleşen)
                out = next_events_at_venue_db(vids[0], limit=limit)
                return {
                    "intent": decision.intent, 
                    "query": q,
                    "events": out
                }

        if decision.intent == Intent.venues_near:
            coords_list = resolve_coords_from_text_or_cities()
            if not coords_list:
                raise HTTPException(status_code=422, detail={"message":"Konum bulunamadı", "query": q})
            
            la, lo = coords_list[0]
            out = venues_near_db(la, lo, radius_km=radius_km, limit=limit)
            return {
                "intent": decision.intent, 
                "query": q,
                "venues": out
            }

        # Fallback
        raise HTTPException(status_code=400, detail={"message":"Desteklenmeyen intent", "intent": decision.intent, "query": q})
        
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": f"Agent query hatası: {str(e)}", "query": q})
