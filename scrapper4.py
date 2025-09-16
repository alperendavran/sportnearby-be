# scrapper.py
import asyncio
import json
import sys
import argparse
import re
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import aiohttp
from aiohttp import ClientResponseError
from bs4 import BeautifulSoup

BASE = "https://www.proleague.be"
EU = ZoneInfo("Europe/Brussels")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "nl,en;q=0.9,fr;q=0.8",
}

# --------- SABİT STADYUM EŞLEŞMESİ (kaynaklı) ---------
VENUE_BY_TEAM_RAW = {
    "OH Leuven Women": {
        "venue": "King Power at Den Dreef Stadium",
        "city": "Heverlee (Leuven)",
        "address": "Kardinaal Mercierlaan 46, 3001 Leuven",
        # Kaynak: OHL "Stadion" sayfası (adres Den Dreef)
        # https://www.ohl.be/nl/stadion
    },
    "Essevee Women": {
        "venue": "The Farm (SV Zulte Waregem trainingscomplexi)",
        "city": "Waregem",
        "address": "Kastanjelaan 75, 9870 Zulte",
        # Not: Maçlar düzenli olarak The Farm’da oynanıyor; kulüp iletişim sayfalarında yer/tesis adı geçiyor,
        # adres bilgisi resmî olarak listelenmediği için şimdilik None bırakıldı.
    },
    "KAA Gent Ladies": {
        "venue": "Chillax Arena (PGB-stadion)",
        "city": "Gent-Oostakker",
        "address": "Eikstraat 85A, 9041 Gent",
        # Kaynak: KAA Gent (supporters) inf sayfası PGB-stadion adresi
        # https://www.kaa-gent.supporters.be/informatie/pgb-stadion-chillax-arena
    },
    "KRC Genk Ladies": {
        "venue": "KRC Genk Jeugdcomplex",
        "city": "Genk",
        "address": "Gouverneur Alex Galopinstraat 13, 3600 Genk",
        # Kaynak: KRC Genk jeugdcomplex adresi (firma/tesis kaydı)
        # https://www.companyweb.be/nl/bedrijf/krc-genk-jeugd-nv/0461289860
    },
    "RSC Anderlecht Women": {
        "venue": "RSCA Belfius Academy (Neerpede)",
        "city": "Anderlecht (Bruxelles)",
        "address": "Drève Olympique 1, 1070 Anderlecht",
        # Kaynak: RSCA Belfius Academy adresi
        # https://www.belfiusacademy.rsca.be/nl/contact
    },
    "Club YLA": {
        "venue": "The Stadium Roeselare (Schiervelde)",
        "city": "Roeselare",
        "address": "Diksmuidsesteenweg 374, 8800 Roeselare",
        # Not: Club YLA’nın iç saha maçları Roeselare tesislerinde oynanıyor; stadyum bilgisi için Schiervelde/The Stadium referansı.
        # Adresi resmî Club YLA sayfasından açıkça teyit edemedim, bu yüzden şimdilik None.
        # Kaynak (stadyum bilgisi): https://deroeselarenaar.be/the-stadium/
    },
    "Standard Femina": {
        "venue": "SL16 Football Campus (Académie RLD)",
        "city": "Rocourt / Liège",
        "address": "Rue de la Tonne 80, 4000 Rocourt (Liège)",
        # Kaynak: Voetbal Vlaanderen – Terreinen (SL16/Standard fem. kampüsü adresi)
        # https://www.voetbalvlaanderen.be/club/01019/terreinen
    },
    "KVC Westerlo Ladies": {
        "venue": "Jeugdcomplex KVC Westerlo (’t Kuipje kompleksinin yanında)",
        "city": "Westerlo",
        "address": "De Merodedreef 189, 2260 Westerlo",
        # Not: Yeni yükselen ekip; kadınların iç saha maçları ağırlıkla gençlik kompleksinde.
        # Resmî sayfada sabit adres/tribün bilgisi yayınlandığında doldururuz.
    },
}

def _norm_team_name(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.lower()
    # aksan/punktuasyon basit normalize
    s = "".join(ch for ch in s if ch.isalnum() or ch.isspace())
    return " ".join(s.split())

VENUE_BY_TEAM_NORM = {_norm_team_name(k): v for k, v in VENUE_BY_TEAM_RAW.items()}

def _venue_for_team(team_name: Optional[str]) -> Dict[str, Optional[str]]:
    info = VENUE_BY_TEAM_NORM.get(_norm_team_name(team_name))
    return info or {"venue": None, "city": None, "address": None}

# =========================
# Low-level HTTP (retry)
# =========================
async def _req_text(session: aiohttp.ClientSession, url: str, max_try: int = 3, timeout: int = 25) -> str:
    last = None
    for i in range(max_try):
        try:
            async with session.get(url, headers=HEADERS, timeout=timeout) as r:
                if r.status >= 500:
                    raise ClientResponseError(r.request_info, r.history, status=r.status, message="server error", headers=r.headers)
                r.raise_for_status()
                return await r.text()
        except Exception as e:
            last = e
            await asyncio.sleep(0.6 * (i + 1))
    raise last

async def _req_json(session: aiohttp.ClientSession, url: str, max_try: int = 3, timeout: int = 25) -> Any:
    last = None
    for i in range(max_try):
        try:
            async with session.get(url, headers=HEADERS, timeout=timeout) as r:
                if r.status >= 500:
                    raise ClientResponseError(r.request_info, r.history, status=r.status, message="server error", headers=r.headers)
                r.raise_for_status()
                ctype = r.headers.get("Content-Type", "")
                if "application/json" in ctype:
                    return await r.json()
                return json.loads(await r.text())
        except Exception as e:
            last = e
            await asyncio.sleep(0.6 * (i + 1))
    raise last

# =========================
# Next.js helpers
# =========================
def _extract_next_data(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag:
        raise RuntimeError("__NEXT_DATA__ script not found (cookie/consent sayfası olabilir)")
    raw = tag.string or tag.get_text() or ""
    data = json.loads(raw)
    page_props = data.get("pageProps") or data.get("props", {}).get("pageProps")
    return {"pageProps": page_props or {}, "buildId": data.get("buildId")}

async def get_build_id(session: aiohttp.ClientSession) -> str:
    html = await _req_text(session, f"{BASE}/lotto-super-league-kalender")
    nd = _extract_next_data(html)
    bid = nd.get("buildId")
    if not bid:
        soup = BeautifulSoup(html, "html.parser")
        tag = soup.find("script", id="__NEXT_DATA__")
        raw = tag.string or tag.get_text() or ""
        j = json.loads(raw)
        bid = j.get("buildId")
    if not bid:
        raise RuntimeError("buildId bulunamadı (muhtemel cookie/consent)")
    return bid

# =========================
# Kalender -> edition/round/gameweeks
# =========================
async def fetch_gameweeks(session: aiohttp.ClientSession, locale: str = "nl") -> Dict[str, Any]:
    html = await _req_text(session, f"{BASE}/lotto-super-league-kalender")
    nd = _extract_next_data(html)

    pp = nd.get("pageProps") or {}
    d = pp.get("data") or {}
    if not d:
        raise RuntimeError("pageProps.data bulunamadı (cookie/consent sayfası olabilir)")

    gameweeks = d.get("gameweeks")
    if not gameweeks:
        page = d.get("page", {})
        for grid in page.get("grids", []) or []:
            for area in grid.get("areas", []) or []:
                for mod in area.get("modules", []) or []:
                    gw = (mod.get("data") or {}).get("gameweeks")
                    if isinstance(gw, list) and gw:
                        gameweeks = gw
                        break
                if gameweeks: break
            if gameweeks: break

    out_gw = []
    for gw in (gameweeks or []):
        out_gw.append({
            "id": gw["id"],
            "name": gw.get("name"),
            "shortName": gw.get("shortName"),
            "week": gw.get("week"),
            "round": (gw.get("round") or {}),
        })

    round_id = d.get("roundId")
    if not round_id and out_gw:
        rid = out_gw[0].get("round", {}).get("id")
        if rid:
            round_id = rid

    edition_id = d.get("editionId")
    if not edition_id:
        def find_edition_in_meta(container):
            for item in container or []:
                if (item.get("target") == "football"
                    and item.get("targetEntity") == "edition"
                    and item.get("targetEntityId")):
                    return item["targetEntityId"]
            return None

        edition_id = find_edition_in_meta(d.get("metadataCollection"))
        if not edition_id:
            page = d.get("page", {})
            for grid in page.get("grids", []) or []:
                for area in grid.get("areas", []) or []:
                    for mod in area.get("modules", []) or []:
                        sd = mod.get("singleData") or {}
                        eid = find_edition_in_meta(sd.get("metadataCollection"))
                        if eid:
                            edition_id = eid
                            break
                    if edition_id: break
                if edition_id: break

        if not edition_id:
            matches = d.get("matches") or []
            if matches:
                g = (matches[0].get("game") or matches[0])
                edition_id = ((g.get("edition") or {}).get("id"))

    return {
        "locale": locale,
        "editionId": edition_id,
        "roundId": round_id,
        "gameweeks": out_gw,
        "buildId": nd.get("buildId"),
    }

def _norm_week_value(gw: Dict[str, Any]) -> Optional[int]:
    if not gw:
        return None
    if isinstance(gw.get("week"), int):
        return gw["week"]
    s = (gw.get("shortName") or gw.get("name") or "").strip()
    if s.startswith("S") and s[1:].isdigit():
        return int(s[1:])
    if s.isdigit():
        return int(s)
    if "Speeldag" in s:
        digits = "".join(ch for ch in s if ch.isdigit())
        if digits.isdigit():
            return int(digits)
    return None

# =========================
# Week list endpoint (variant_a)
# =========================
def build_week_url(locale: str, edition_id: str, round_id: str, gameweek_id: str) -> str:
    return (f"{BASE}/api/football_list/football_competition_match/variant_a"
            f"?locale={locale}"
            f"&editionId={edition_id}"
            f"&roundId={round_id}"
            f"&groupIds="
            f"&gameweekId={gameweek_id}")

async def fetch_matches_for_gameweek(
    session: aiohttp.ClientSession,
    edition_id: Optional[str],
    round_id: Optional[str],
    gameweek_id: str,
    locale: str = "nl",
) -> List[Dict[str, Any]]:
    # Normal yol: variant_a
    if edition_id and round_id:
        url = build_week_url(locale, edition_id, round_id, gameweek_id)
        j = await _req_json(session, url)
        data = j.get("data") or j
        matches = data.get("matches") or data.get("items") or []
        out = []
        for m in matches:
            g = m.get("game", m)
            gw_obj = (g.get("gameweek") or {})
            # week numeric
            week_num: Optional[int] = None
            if isinstance(gw_obj, dict):
                if isinstance(gw_obj.get("week"), int):
                    week_num = gw_obj["week"]
                else:
                    week_num = _norm_week_value({"shortName": gw_obj.get("shortName"), "name": gw_obj.get("name")})

            out.append({
                "slug": g.get("slug"),
                "date": g.get("date"),   # 'YYYY-MM-DD'
                "time": g.get("time"),   # ISO '...Z' veya 'HH:MM' gelebilir
                "home": (g.get("homeTeam") or {}).get("name"),
                "away": (g.get("awayTeam") or {}).get("name"),
                "gameweek": gw_obj.get("shortName") or gw_obj.get("week"),
                "week": week_num,
                "competition": (g.get("competition") or {}).get("name"),
            })
        return out

    # Fallback: HTML içinden (gerekirse)
    html = await _req_text(session, f"{BASE}/lotto-super-league-kalender")
    nd = _extract_next_data(html)
    d = (nd.get("pageProps") or {}).get("data") or {}

    matches = d.get("matches") or []
    out = []
    for m in matches:
        g = m.get("game", m)
        gw = (g.get("gameweek") or {})
        out.append({
            "slug": g.get("slug"),
            "date": g.get("date"),
            "time": g.get("time"),
            "home": (g.get("homeTeam") or {}).get("name"),
            "away": (g.get("awayTeam") or {}).get("name"),
            "gameweek": gw.get("shortName") or gw.get("week"),
            "week": gw.get("week"),
            "competition": (g.get("competition") or {}).get("name"),
        })
    return out

# =========================
# Saat/Tarih dönüştürücü
# =========================
_HHMM_RE = re.compile(r"^\d{1,2}:\d{2}$")

def _to_local_utc(time_field: Optional[str], date_fallback: str) -> Tuple[datetime, datetime]:
    """
    time_field:
      - ISO UTC (örn '2025-09-20T13:30:00Z') -> direkt parse
      - 'HH:MM' -> Europe/Brussels lokalde kabul et, UTC'ye çevir
      - None -> 20:00 UTC varsay
    date_fallback: 'YYYY-MM-DD'
    """
    if time_field:
        ts = time_field.strip()
        if "T" in ts or ts.endswith("Z"):
            dt_utc = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            dt_local = dt_utc.astimezone(EU)
            return dt_local, dt_utc
        if _HHMM_RE.match(ts):
            # yerel saat
            dt_local = datetime.strptime(f"{date_fallback} {ts}", "%Y-%m-%d %H:%M").replace(tzinfo=EU)
            dt_utc = dt_local.astimezone(timezone.utc)
            return dt_local, dt_utc
    # saat yok
    dt_utc = datetime.fromisoformat(f"{date_fallback}T20:00:00+00:00")
    dt_local = dt_utc.astimezone(EU)
    return dt_local, dt_utc

# =========================
# Public: list matches by week(s)
# =========================
async def list_week_matches(
    target_weeks: List[int],
    locale: str = "nl",
    concurrency: int = 8,   # artık detay çağrısı yok ama arayüz uyumu için bırakıldı
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []

    async with aiohttp.ClientSession() as session:
        meta = await fetch_gameweeks(session, locale=locale)
        edition_id = meta["editionId"]
        round_id = meta["roundId"]
        gameweeks = meta["gameweeks"]
        # build_id = meta.get("buildId")  # detay sayfasını kullanmıyoruz

        # map: week -> gameweek_id
        week_to_id: Dict[int, str] = {}
        for gw in gameweeks:
            w = _norm_week_value(gw)
            if isinstance(w, int):
                week_to_id[w] = gw["id"]

        selected_ids = []
        for tw in target_weeks:
            if tw not in week_to_id:
                print(f"[WARN] Week {tw} bulunamadı; atlanıyor.", file=sys.stderr)
                continue
            selected_ids.append(week_to_id[tw])

        # 1) haftalık listeler
        all_matches: List[Dict[str, Any]] = []
        for gw_id in selected_ids:
            week_matches = await fetch_matches_for_gameweek(session, edition_id, round_id, gw_id, locale=locale)
            all_matches.extend(week_matches)

        # uniq slug
        seen = set()
        unique = []
        for m in all_matches:
            slug = m.get("slug")
            key = slug or f"{m.get('date')}|{m.get('home')}|{m.get('away')}"
            if key not in seen:
                seen.add(key)
                unique.append(m)

        # 2) Detay sayfasına gitmeden kayıtları oluştur
        detailed: List[Dict[str, Any]] = []
        for m in unique:
            dt_local, dt_utc = _to_local_utc(m.get("time"), m.get("date"))
            home = m.get("home")
            venue_info = _venue_for_team(home)

            detailed.append({
                "match_name": f"{home} vs {m.get('away')}",
                "date_local": dt_local.strftime("%Y-%m-%d"),
                "time_local": dt_local.strftime("%H:%M"),
                "date_utc": dt_utc.strftime("%Y-%m-%d"),
                "time_utc": dt_utc.strftime("%H:%M"),
                "venue": venue_info["venue"],
                "venue_city": venue_info["city"],
                "competition": m.get("competition"),
                "week": m.get("week"),
                "gameweek": m.get("gameweek"),
                "venue_address": venue_info["address"],
                "slug": m.get("slug"),
            })

        # haftaya + tarihe göre sırala
        def sort_key(x: Dict[str, Any]):
            return (x.get("week") or 0, x["date_utc"], x["time_utc"])
        detailed.sort(key=sort_key)

        results.extend(detailed)
    return results

# =========================
# CLI
# =========================
def parse_args():
    ap = argparse.ArgumentParser(description="Lotto Super League haftalık maç toplama (kalender -> liste, venue fallback).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--week", type=int, help="Tek hafta (örn: 3)")
    g.add_argument("--weeks", type=str, help="Virgüllü haftalar (örn: 3,4,5)")
    g.add_argument("--all", action="store_true", help="Tüm haftalar")
    ap.add_argument("--locale", type=str, default="nl", choices=["nl","fr","en"], help="Dil parametresi (variant_a için)")
    ap.add_argument("--save", type=str, help="JSON çıktı dosyası")
    ap.add_argument("--concurrency", type=int, default=8, help="(Kullanılmıyor) arayüz uyumu")
    return ap.parse_args()

def main():
    args = parse_args()
    if args.week:
        weeks = [args.week]
    elif args.weeks:
        weeks = [int(x.strip()) for x in args.weeks.split(",") if x.strip().isdigit()]
        if not weeks:
            print("Geçerli --weeks verin, örn: --weeks 3,4,5", file=sys.stderr)
            sys.exit(2)
    else:
        # --all: 1..40 gibi makul bir aralık deneriz; olmayanlar zaten atlanır
        weeks = list(range(1, 21))

    out = asyncio.run(list_week_matches(weeks, locale=args.locale, concurrency=args.concurrency))

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"Kaydedildi: {args.save}")
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
