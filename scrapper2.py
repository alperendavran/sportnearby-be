import requests, json
from datetime import datetime
from dateutil import tz

API_BASE = "https://bnxt.sportpress.info/api/v1"

CLUB_IDS = {"BE": 1, "NL": 2}

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36",
    "Origin": "https://bnxtleague.com",
    "Referer": "https://bnxtleague.com/en/calendar",
    "X-Authorization": "BWSyE7sgg9QAurh2JX9cpjzjGc652BWLuNUS",  # tarayıcıdaki ile aynı
    "X-Localization": "en",
}

def fetch_schedule_by_club(season: int = 2026, clubs=(1, 2), month: int = -1, lang: str = "en"):
    url = f"{API_BASE}/schedule/club/{season}"

    # clubs[0]=1&clubs[1]=2 şeklinde parametreleri kur
    params = [("lang", lang)] + [(f"clubs[{i}]", c) for i, c in enumerate(clubs)] + [("month", month)]

    # X-Localization'ı seçtiğin dile göre ayarla
    headers = {**HEADERS, "X-Localization": lang}

    resp = requests.get(url, params=params, headers=headers, timeout=20)
    if resp.status_code == 401:
        raise RuntimeError(f"401 Unauthorized. Büyük olasılık X-Authorization/X-Localization/Origin başlıkları eksik ya da değişti.\nBody: {resp.text}")
    resp.raise_for_status()
    return resp.json().get("data", [])

def normalize_row(game, local_tz: str = None):
    dt = datetime.strptime(game["game_time"], "%Y-%m-%d %H:%M:%S")
    dt_utc = dt.replace(tzinfo=tz.gettz("UTC"))
    dt_local = dt_utc.astimezone(tz.gettz(local_tz)) if local_tz else dt_utc
    
    home = next((c for c in game["competitors"] if c.get("side") == 1), None)
    away = next((c for c in game["competitors"] if c.get("side") == 2), None)
    
    def team(c):
        if not c: return None
        return c["competition_team"]["name"]
    
    h_name = team(home)
    a_name = team(away)
    
    return {
        "match_name": f"{h_name} vs {a_name}",
        "date_local": dt_local.strftime("%Y-%m-%d"),
        "time_local": dt_local.strftime("%H:%M"),
        "date_utc": dt_utc.strftime("%Y-%m-%d"),
        "time_utc": dt_utc.strftime("%H:%M"),
        "venue": (game.get("arena") or {}).get("name"),
        "venue_city": None,  # BNXT League'de şehir bilgisi yok
        "competition": (game.get("competition") or {}).get("name"),
        "week": None,  # BNXT League'de hafta kavramı yok
        "match_id": game["id"],
    }

def get_calendar(season=2026, clubs=("BE","NL"), month=-1, lang="en", local_tz="Europe/Brussels"):
    club_ids = [CLUB_IDS.get(c, c) for c in clubs]
    raw = fetch_schedule_by_club(season=season, clubs=club_ids, month=month, lang=lang)
    rows = [normalize_row(g, local_tz=local_tz) for g in raw]
    rows.sort(key=lambda r: (r["date_local"], r["time_local"]))
    return rows

if __name__ == "__main__":
    data = get_calendar(season=2026, clubs=("BE","NL"), month=-1, lang="en", local_tz="Europe/Brussels")
    print(json.dumps(data, ensure_ascii=False, indent=2))
