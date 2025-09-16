# scrapper3.py
import re
import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import pandas as pd
from io import StringIO

BASE = "https://statistics.lottovolleyleague.be"

COMP = {
    "men":   {"id": 38, "pid": 84, "name": "LOTTO VOLLEY LEAGUE MEN"},
    "women": {"id": 40, "pid": 86, "name": "BELGIAN VOLLEY LEAGUE WOMEN"},
}

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://lottovolleyleague.be/",
    "Accept-Language": "en-US,en;q=0.9",
})

@dataclass
class MatchRow:
    leg: Optional[str]
    datetime: Optional[str]
    arena: Optional[str]
    home: Optional[str]
    away: Optional[str]
    match_id: Optional[int]
    match_url: Optional[str]

def fetch(url: str, params: Optional[dict] = None) -> str:
    r = session.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.text

def parse_matches_html(html: str, comp_id: int, pid: int) -> List[MatchRow]:
    soup = BeautifulSoup(html, "lxml")
    out: List[MatchRow] = []

    # Leg başlıkları (h3'lerde “LEG 01” vs)
    leg_headers = soup.find_all("h3")
    # Leg başlığından sonraki kutu içinde aynı ctrl indeksli hidden inputlar var.
    # Ama robust yapmak için tüm matchRow'ları gezip en yakın önceki hiddenları alacağız.
    for row in soup.select('div[id$="_MatchRow"]'):
        # Leg adı (en yakın yukarıdaki h3’ü bul)
        leg = None
        prev = row
        while prev:
            prev = prev.find_previous()
            if prev and prev.name == "h3" and "LEG" in prev.get_text(strip=True):
                leg = prev.get_text(strip=True)
                break

        # mID (onclick içindeki MatchStatistics.aspx?mID=XXXX)
        mid = None
        click_div = row.select_one('div[onclick*="MatchStatistics.aspx"]')
        if click_div and click_div.has_attr("onclick"):
            m = re.search(r"mID=(\d+)", click_div["onclick"])
            if m: mid = int(m.group(1))

        # Tarih-saat: önce satır içindeki span’lar, olmazsa en yakın hidden input
        def first_text(*selectors):
            for sel in selectors:
                el = row.select_one(sel)
                if el and el.get_text(strip=True):
                    return el.get_text(strip=True)
            return None

        dt = first_text(
            'span[id$="_LB_DataOra"]',
            'span[id$="_LB_DataOra_sm"]',
            'span[id$="_LB_DataOra_md"]'
        )
        if not dt:
            prev_dt = row.find_previous(lambda t: t.name == "input" and t.get("id","").endswith("_HF_MatchDatetime"))
            if prev_dt:
                dt = prev_dt.get("value")

        arena = first_text('span[id$="_LB_Palasport"]')

        # Takım isimleri (farklı id’ler olabiliyor; iki varyanta da bak)
        home = first_text('span[id$="_LBL_HomeTeamName"]', 'span[id$="Label2"]')
        away = first_text('span[id$="_LBL_GuestTeamName"]', 'span[id$="Label4"]')

        match_url = None
        if mid:
            # CID param’ı sayfa içindeki leg kimliği olabilir ama MatchStatistics için şart değil.
            match_url = f"{BASE}/MatchStatistics.aspx?mID={mid}&ID={comp_id}&PID={pid}"

        out.append(MatchRow(
            leg=leg, datetime=dt, arena=arena, home=home, away=away,
            match_id=mid, match_url=match_url
        ))

    return out

def get_matches(comp: str) -> List[Dict]:
    cid, pid = COMP[comp]["id"], COMP[comp]["pid"]
    url = f"{BASE}/CompetitionMatches.aspx"
    html = fetch(url, params={"ID": cid, "PID": pid})
    rows = parse_matches_html(html, comp_id=cid, pid=pid)
    return [asdict(r) for r in rows]

def get_standings(comp: str) -> pd.DataFrame:
    """Önce pandas.read_html ile dener, tablo yoksa BS4 fallback kullanır."""
    cid, pid = COMP[comp]["id"], COMP[comp]["pid"]
    url = f"{BASE}/CompetitionStandings.aspx?ID={cid}&PID={pid}"
    html = fetch(url)

    # 1) Pandas ile (en yaygın sınıf RadGrid'in ana tablosu)
    try:
        # doğrudan URL de verilebilir ama bazı durumlarda text’ten daha stabil
        dfs = pd.read_html(StringIO(html), match="Team|Puan|Points|Ranking", flavor="lxml")
        if dfs:
            # bazı sayfalarda birden çok tablo gelebilir; en genişini seç
            df = max(dfs, key=lambda d: d.shape[1] * d.shape[0])
            return df
    except ValueError:
        pass  # tablo bulunamadı

    # 2) BS4 fallback: RadGrid içinde satırları elle çek
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.rgMasterTable") or soup.find("table")
    if not table:
        raise RuntimeError("Standings table not found in HTML (grid empty or rendered via JS).")

    headers = [th.get_text(strip=True) for th in table.select("thead th")] or \
              [th.get_text(strip=True) for th in table.select("tr th")]
    rows = []
    for tr in table.select("tbody tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.select("td")]
        if cells:
            rows.append(cells)
    df = pd.DataFrame(rows, columns=headers[:len(rows[0])] if rows and headers else None)
    return df

# --- ADD: utils to normalize & save ------------------------------------------
from datetime import datetime
import pytz
from pathlib import Path

BRUSSELS = pytz.timezone("Europe/Brussels")

def normalize_matches(rows, tz=BRUSSELS):
    """dd/mm/yyyy - HH:MM -> standart format"""
    out = []
    for r in rows:
        dt_local = None
        dt_utc = None
        date_local = None
        time_local = None
        date_utc = None
        time_utc = None
        
        if r["datetime"]:
            # '18/10/2025 - 20:30' -> datetime
            dt = datetime.strptime(r["datetime"], "%d/%m/%Y - %H:%M")
            dt_local = tz.localize(dt)
            dt_utc = dt_local.astimezone(pytz.UTC)
            
            date_local = dt_local.strftime("%Y-%m-%d")
            time_local = dt_local.strftime("%H:%M")
            date_utc = dt_utc.strftime("%Y-%m-%d")
            time_utc = dt_utc.strftime("%H:%M")
        
        # Leg'den hafta numarasını çıkar
        week = None
        if r["leg"] and "LEG" in r["leg"]:
            import re
            match = re.search(r"LEG\s*(\d+)", r["leg"])
            if match:
                week = int(match.group(1))
        
        out.append({
            "match_name": f"{r['home']} vs {r['away']}",
            "date_local": date_local,
            "time_local": time_local,
            "date_utc": date_utc,
            "time_utc": time_utc,
            "venue": r["arena"],
            "venue_city": None,  # Volley League'de şehir bilgisi yok
            "competition": "LOTTO VOLLEY LEAGUE MEN" if "men" in str(r) else "BELGIAN VOLLEY LEAGUE WOMEN",
            "week": week,
            "leg": r["leg"],
            "match_id": r["match_id"],
            "match_url": r["match_url"],
        })
    return out

def clean_standings_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    read_html çok başlıklı kolonlar üretebiliyor (Unnamed_*). 
    Kolonları düzleştirip gereksiz satırları atıyoruz.
    """
    # 1) Çok başlıklı kolonları düzleştir
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            " ".join([str(c) for c in tup if "Unnamed" not in str(c)]).strip()
            for tup in df.columns.to_list()
        ]
    else:
        df.columns = [str(c).strip() for c in df.columns]

    # 2) Takım adı boş olan satırları at
    team_col = next((c for c in df.columns if c.lower().startswith("team") or "Team" in c), None)
    if team_col:
        df = df[~df[team_col].isna()].copy()

    # 3) '-' ve boşlukları NaN yap, sayısal kolonları sayıya çevir
    df = df.replace({"-": pd.NA, "–": pd.NA, "": pd.NA})
    for c in df.columns:
        if c != team_col:
            df[c] = pd.to_numeric(df[c], errors="ignore")

    # 4) kolon isimlerini biraz standartlaştır
    ren = {
        "Team": "Team",
        "Played": "P",
        "Won": "W",
        "Lost": "L",
        "Sets Won": "SW",
        "Sets Lost": "SL",
        "Points": "Pts",
        "Ranking": "Rank",
        "Penalty": "Penalty",
    }
    df = df.rename(columns={k: v for k, v in ren.items() if k in df.columns})

    return df.reset_index(drop=True)

def save_json(obj, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def save_csv(df, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
# -----------------------------------------------------------------------------


if __name__ == "__main__":
    men_matches_raw = get_matches("men")
    women_matches_raw = get_matches("women")

    # Erkek maçları için competition bilgisini düzelt
    men_matches = normalize_matches(men_matches_raw)
    for match in men_matches:
        match["competition"] = "LOTTO VOLLEY LEAGUE MEN"
    
    # Kadın maçları için competition bilgisini düzelt  
    women_matches = normalize_matches(women_matches_raw)
    for match in women_matches:
        match["competition"] = "BELGIAN VOLLEY LEAGUE WOMEN"

    print(f"Men matches: {len(men_matches)}  | Women matches: {len(women_matches)}")
    print(json.dumps(men_matches[:3], ensure_ascii=False, indent=2))

    # standings (both)
    women_standings_raw = get_standings("women")
    women_standings = clean_standings_df(women_standings_raw)

    men_standings_raw = get_standings("men")
    men_standings = clean_standings_df(men_standings_raw)

    # save
    save_json(men_matches,   "out/volley_men_matches.json")
    save_json(women_matches, "out/volley_women_matches.json")
    save_csv(women_standings, "out/volley_women_standings.csv")
    save_csv(men_standings,   "out/volley_men_standings.csv")

    print("✓ Dosyalar yazıldı: out/*.json, out/*.csv")
