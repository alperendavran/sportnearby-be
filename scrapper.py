# scrapper.py
import asyncio
import json
import sys
import argparse
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
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
    """
    __NEXT_DATA__ JSON'unu güvenli çıkartır. Next 12/13 farklarını tolere eder.
    Dönen dict her zaman {"pageProps":..., "buildId": "..."} şeklinde normalize edilir.
    """
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag:
        raise RuntimeError("__NEXT_DATA__ script not found (cookie/consent sayfası olabilir)")
    raw = tag.string or tag.get_text() or ""
    data = json.loads(raw)

    page_props = data.get("pageProps")
    if not page_props:
        page_props = data.get("props", {}).get("pageProps")

    out = {"pageProps": page_props or {}, "buildId": data.get("buildId")}
    return out

async def get_build_id(session: aiohttp.ClientSession) -> str:
    html = await _req_text(session, f"{BASE}/jpl-kalender")
    nd = _extract_next_data(html)
    bid = nd.get("buildId")
    if not bid:
        # bazı Next konfiglerinde buildId üst seviyede bulunmayabilir; ham JSON tekrar denenir
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
    """
    /jpl-kalender üzerinden:
    - editionId (çoklu fallback ile)
    - roundId  (gameweeks[*].round.id fallback)
    - gameweeks: [{id, name, shortName, week}]
    - buildId
    """
    html = await _req_text(session, f"{BASE}/jpl-kalender")
    nd = _extract_next_data(html)

    pp = nd.get("pageProps") or {}
    d = pp.get("data") or {}
    if not d:
        raise RuntimeError("pageProps.data bulunamadı (cookie/consent sayfası olabilir)")

    # 1) gameweeks'i topla
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

    # 2) roundId fallback: ilk gameweek.round.id
    round_id = d.get("roundId")
    if not round_id and out_gw:
        rid = out_gw[0].get("round", {}).get("id")
        if rid:
            round_id = rid

    # 3) editionId için güçlü fallback zinciri
    edition_id = d.get("editionId")
    if not edition_id:
        # a) metadataCollection’da edition kaydı
        def find_edition_in_meta(container):
            for item in container or []:
                if (item.get("target") == "football"
                    and item.get("targetEntity") == "edition"
                    and item.get("targetEntityId")):
                    return item["targetEntityId"]
            return None

        # page.metadataCollection
        edition_id = find_edition_in_meta(d.get("metadataCollection"))
        # page.grids[].areas[].modules[].singleData.metadataCollection
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

        # b) gameweeks → bazen aynı yapıda edition üstte bulunur; yoksa None kalabilir
        # c) son çare: d['matches'] varsa ilk kaydın edition.id’sini kullan
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
            out.append({
                "slug": g.get("slug"),
                "date": g.get("date"),
                "time": g.get("time"),
                "home": (g.get("homeTeam") or {}).get("name"),
                "away": (g.get("awayTeam") or {}).get("name"),
                "gameweek": (g.get("gameweek") or {}).get("shortName") or (g.get("gameweek") or {}).get("week"),
                "competition": (g.get("competition") or {}).get("name"),
            })
        return out

    # Fallback: /jpl-kalender HTML → __NEXT_DATA__ → pageProps.data.matches filtresi
    html = await _req_text(session, f"{BASE}/jpl-kalender")
    nd = _extract_next_data(html)
    d = (nd.get("pageProps") or {}).get("data") or {}

    matches = d.get("matches") or []
    out = []
    for m in matches:
        g = m.get("game", m)
        gw = (g.get("gameweek") or {})
        if gw.get("id") == gameweek_id:
            out.append({
                "slug": g.get("slug"),
                "date": g.get("date"),
                "time": g.get("time"),
                "home": (g.get("homeTeam") or {}).get("name"),
                "away": (g.get("awayTeam") or {}).get("name"),
                "gameweek": gw.get("shortName") or gw.get("week"),
                "competition": (g.get("competition") or {}).get("name"),
            })
    return out


# =========================
# Detail fetch (robust: next-data -> HTML)
# =========================
def _pick_game_from_next_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Standart yer
    try:
        return payload["pageProps"]["data"]["game"]
    except Exception:
        pass

    # Son çare: derin arama
    def walk(x):
        if isinstance(x, dict):
            ks = set(x.keys())
            if {"homeTeam", "awayTeam", "date", "time"} <= ks and "competition" in ks:
                return x
            for v in x.values():
                r = walk(v)
                if r:
                    return r
        elif isinstance(x, list):
            for it in x:
                r = walk(it)
                if r:
                    return r
        return None

    return walk(payload) or {}

async def fetch_detail_for_slug(
    session: aiohttp.ClientSession,
    slug: str,
    build_id: Optional[str],
) -> Dict[str, Any]:
    # 1) _next/data dene
    if build_id:
        next_url = f"{BASE}/_next/data/{build_id}/wedstrijden/{slug}.json?params=wedstrijden&params={slug}"
        try:
            dj = await _req_json(session, next_url)
            game = _pick_game_from_next_json(dj)
            if game:
                return game
        except Exception:
            pass
    # 2) HTML fallback
    html_url = f"{BASE}/wedstrijden/{slug}"
    html = await _req_text(session, html_url)
    nd = _extract_next_data(html)
    game = _pick_game_from_next_json(nd)
    if not game:
        # belki HTML'deki __NEXT_DATA__ ham JSON'u gerekir
        soup = BeautifulSoup(html, "html.parser")
        tag = soup.find("script", id="__NEXT_DATA__")
        raw = tag.string or tag.get_text() or ""
        game = _pick_game_from_next_json(json.loads(raw))
    if not game:
        raise RuntimeError(f"Detay JSON'da game bulunamadı: {slug}")
    return game

def _to_local_utc(time_iso: Optional[str], date_fallback: str) -> Tuple[datetime, datetime]:
    if time_iso:
        dt_utc = datetime.fromisoformat(time_iso.replace("Z", "+00:00"))
    else:
        # saat yoksa 20:00 UTC varsayımı
        dt_utc = datetime.fromisoformat(f"{date_fallback}T20:00:00+00:00")
    dt_local = dt_utc.astimezone(EU)
    return dt_local, dt_utc

# =========================
# Public: list matches by week(s)
# =========================
async def list_week_matches(
    target_weeks: List[int],
    locale: str = "nl",
    concurrency: int = 8,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    sem = asyncio.Semaphore(concurrency)

    async with aiohttp.ClientSession() as session:
        # meta
        meta = await fetch_gameweeks(session, locale=locale)
        edition_id = meta["editionId"]
        round_id = meta["roundId"]
        gameweeks = meta["gameweeks"]
        build_id = meta.get("buildId")

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

        # 1) hafta listelerinden slug'ları çek
        all_matches: List[Dict[str, Any]] = []
        for gw_id in selected_ids:
            week_matches = await fetch_matches_for_gameweek(session, edition_id, round_id, gw_id, locale=locale)
            all_matches.extend(week_matches)

        # uniq slug listesi
        seen = set()
        unique = []
        for m in all_matches:
            slug = m.get("slug")
            if slug and slug not in seen:
                seen.add(slug)
                unique.append(m)

        # 2) detayları paralel çek
        async def _one(m: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            async with sem:
                slug = m["slug"]
                try:
                    game = await fetch_detail_for_slug(session, slug, build_id)
                    dt_local, dt_utc = _to_local_utc(game.get("time"), game.get("date"))
                    home_team = game.get("homeTeam", {}).get("name")
                    away_team = game.get("awayTeam", {}).get("name")
                    return {
                        "match_name": f"{home_team} vs {away_team}",
                        "date_local": dt_local.strftime("%Y-%m-%d"),
                        "time_local": dt_local.strftime("%H:%M"),
                        "date_utc": dt_utc.strftime("%Y-%m-%d"),
                        "time_utc": dt_utc.strftime("%H:%M"),
                        "venue": (game.get("venue") or {}).get("name") or game.get("venueName"),
                        "venue_city": None,  # Pro League'de şehir bilgisi yok
                        "competition": game.get("competition", {}).get("name"),
                        "week": game.get("gameweek", {}).get("week"),
                        "slug": game.get("slug"),
                    }
                except Exception as e:
                    print(f"[ERR] {slug}: {e}", file=sys.stderr)
                    return None

        tasks = [_one(m) for m in unique if m.get("slug")]
        detailed = [x for x in await asyncio.gather(*tasks) if x]

        # haftaya göre sırala: tarih + saat
        def sort_key(x: Dict[str, Any]):
            return (x.get("week") or 0, x["date_utc"], x["time_utc"])
        detailed.sort(key=sort_key)

        results.extend(detailed)
    return results

# =========================
# CLI
# =========================
def parse_args():
    ap = argparse.ArgumentParser(description="Pro League JPL haftalık maç toplama (kalender -> detay).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--week", type=int, help="Tek hafta (örn: 7)")
    g.add_argument("--weeks", type=str, help="Virgüllü haftalar (örn: 7,8,9)")
    g.add_argument("--all", action="store_true", help="Tüm haftalar")
    ap.add_argument("--locale", type=str, default="nl", choices=["nl","fr","en"], help="Dil parametresi (variant_a için)")
    ap.add_argument("--save", type=str, help="JSON çıktı dosyası")
    ap.add_argument("--concurrency", type=int, default=8, help="Detay çağrıları eşzamanlılık")
    return ap.parse_args()

def main():
    args = parse_args()
    if args.week:
        weeks = [args.week]
    elif args.weeks:
        weeks = [int(x.strip()) for x in args.weeks.split(",") if x.strip().isdigit()]
        if not weeks:
            print("Geçerli --weeks verin, örn: --weeks 7,8,9", file=sys.stderr)
            sys.exit(2)
    else:
        # --all: 1..40 gibi makul bir aralık deneriz; olmayanlar zaten atlanır
        weeks = list(range(1, 40))

    out = asyncio.run(list_week_matches(weeks, locale=args.locale, concurrency=args.concurrency))

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"Kaydedildi: {args.save}")
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
