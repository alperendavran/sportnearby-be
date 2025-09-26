#!/usr/bin/env python3
# -*- coding: utf-8-sig -*-
"""
Tüm scraperların verilerini tek Excel dosyasında birleştirir
Tek sheet'te tüm maçları gösterir ve latitude/longitude bilgilerini ekler
"""

import json
import pandas as pd
from pathlib import Path
import asyncio
import sys
import time
import requests
from datetime import datetime
from typing import Dict, Any, Optional

# Scraper modüllerini import et
from scrapper import list_week_matches as get_jpl_matches
from scrapper2 import get_calendar as get_bnxt_matches
from scrapper3 import get_matches as get_volley_matches, normalize_matches
from scrapper4 import list_week_matches as get_super_league_matches

# Geocoding için gerekli sabitler
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "jointly-venues-geocoder/1.0 (contact: you@example.com)"
VIEWBOX = "2.5,49.4,7.2,54.1"  # BE+NL bounding box
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

# Manuel koordinatlar (verdiğiniz koddan)
MANUAL_COORDINATES: Dict[str, Dict[str, Any]] = {
    "Dender Football Complex": {
        "lat": "50.88423322084203",
        "lon": "4.072707655098375",
        "display_name": "Dender Football Complex, Denderleeuw, Belgium",
        "address": {"country": "Belgium", "city": "Denderleeuw"},
        "class": "leisure",
        "type": "sports_centre"
    },
    "Het Kuipje": {
        "lat": "51.095090989003886", 
        "lon": "4.929020670450795",
        "display_name": "Het Kuipje, Westerlo, Belgium",
        "address": {"country": "Belgium", "city": "Westerlo"},
        "class": "leisure",
        "type": "stadium"
    },
    "COREtec Dôme": {
        "lat": "51.217632774083114",
        "lon": "2.887844297442632", 
        "display_name": "COREtec Dôme, Ostend, Belgium",
        "address": {"country": "Belgium", "city": "Ostend"},
        "class": "leisure",
        "type": "sports_centre"
    },
    "Complexe Sportif Neder-Over-Heembeek": {
        "lat": "50.89334354019493",
        "lon": "4.376596634241141",
        "display_name": "Neder-Over-Heembeek sports complex, Brussels, Belgium", 
        "address": {"country": "Belgium", "city": "Brussels"},
        "class": "leisure",
        "type": "sports_centre"
    },
    "ING Arena": {
        "lat": "50.90131516379589",
        "lon": "4.34203290112698",
        "display_name": "ING Arena (Palais 12), Brussels Expo, Belgium",
        "address": {"country": "Belgium", "city": "Brussels"},
        "class": "leisure", 
        "type": "arena"
    },
    "REO ARENA": {
        "lat": "50.95152111672213",
        "lon": "3.103961439758935",
        "display_name": "REO Arena, Roeselare, Belgium",
        "address": {"country": "Belgium", "city": "Roeselare"},
        "class": "leisure",
        "type": "arena"
    },
    "CENTRE SPORTIF J.MOISSE": {
        "lat": "50.95147380420512",
        "lon": "3.1039828974302335",
        "display_name": "Centre Sportif J. Moisse, Belgium",
        "address": {"country": "Belgium"},
        "class": "leisure",
        "type": "sports_centre"
    },
    "POLE-BALLON DE LA PROVINCE DE LIEGE": {
        "lat": "50.95148056313905",
        "lon": "3.104004355101532",
        "display_name": "Pôle Ballon de la Province de Liège, Belgium",
        "address": {"country": "Belgium", "city": "Liège"},
        "class": "leisure",
        "type": "sports_centre"
    },
    "St Antonius Global Catering Arena": {
        "lat": "50.95146704527017",
        "lon": "3.103918524416338",
        "display_name": "Sint-Antonius Arena, Belgium",
        "address": {"country": "Belgium"},
        "class": "leisure",
        "type": "arena"
    },
    "Sporthal Diepvenneke": {
        "lat": "50.95146704527017",
        "lon": "3.103961439758935",
        "display_name": "Sporthal Diepvenneke, Belgium",
        "address": {"country": "Belgium"},
        "class": "leisure",
        "type": "sports_centre"
    },
    "Sporthal AVERBO": {
        "lat": "50.83169626944279",
        "lon": "3.7680422262603104",
        "display_name": "Sporthal Averbo, Belgium",
        "address": {"country": "Belgium"},
        "class": "leisure",
        "type": "sports_centre"
    },
    "Shape N Go Arena": {
        "lat": "50.29308846476325",
        "lon": "4.329132226235415",
        "display_name": "Shape N Go Arena, Belgium",
        "address": {"country": "Belgium"},
        "class": "leisure",
        "type": "arena"
    },
    "Sporthal AXION": {
        "lat": "51.16235696681756",
        "lon": "4.958169816481738",
        "display_name": "Sporthal Axion, Belgium",
        "address": {"country": "Belgium"},
        "class": "leisure",
        "type": "sports_centre"
    },
    "Topsporthal Meerminnen": {
        "lat": "51.21188837578046",
        "lon": "4.242376237921549",
        "display_name": "Topsporthal De Meerminnen, Beveren, Belgium",
        "address": {"country": "Belgium", "city": "Beveren"},
        "class": "leisure",
        "type": "sports_centre"
    },
    "Salle Ballens ASBL": {
        "lat": "51.211841328795785",
        "lon": "4.242601543470182",
        "display_name": "Salle Ballens, Belgium",
        "address": {"country": "Belgium"},
        "class": "leisure",
        "type": "sports_centre"
    },
    "The Farm (SV Zulte Waregem trainingscomplexi)": {
        "lat": "51.211915259750135",
        "lon": "4.242537170456288",
        "display_name": "The Farm training complex, Zulte, Belgium",
        "address": {"country": "Belgium", "city": "Zulte"},
        "class": "leisure",
        "type": "sports_centre"
    },
    "Chillax Arena (PGB-stadion)": {
        "lat": "51.08959313184206",
        "lon": "3.764907114628803",
        "display_name": "Chillax Arena (PGB-stadion), Oostakker, Ghent, Belgium",
        "address": {"country": "Belgium", "city": "Ghent"},
        "class": "leisure",
        "type": "arena"
    },
    "The Stadium Roeselare (Schiervelde)": {
        "lat": "50.95230138952164",
        "lon": "3.1054288532519907",
        "display_name": "Schiervelde (The Stadium), Roeselare, Belgium",
        "address": {"country": "Belgium", "city": "Roeselare"},
        "class": "leisure",
        "type": "stadium"
    },
    "KVC Westerlo Jeugdcomplex": {
        "lat": "51.13133436429118",
        "lon": "4.85755475066844",
        "display_name": "KVC Westerlo Jeugdcomplex, Westerlo, Belgium",
        "address": {"country": "Belgium", "city": "Westerlo"},
        "class": "leisure",
        "type": "sports_centre"
    },
    "SL16 Football Campus (Académie RLD)": {
        "lat": "50.575987694593216",
        "lon": "5.548811855084096",
        "display_name": "SL16 Football Campus, Rocourt, Liège, Belgium",
        "address": {"country": "Belgium", "city": "Liège"},
        "class": "leisure",
        "type": "sports_centre"
    },
    "RSCA Belfius Academy (Neerpede)": {
        "lat": "50.82481695169476",
        "lon": "4.273805360706652",
        "display_name": "RSCA Belfius Academy, Neerpede, Anderlecht, Belgium",
        "address": {"country": "Belgium", "city": "Anderlecht"},
        "class": "leisure",
        "type": "sports_centre"
    },
    "CC DE STEIGER VAUBAN": {
        "lat": "50.7933023992663",
        "lon": "3.1267425244286216",
        "display_name": "CC De Steiger Vauban, Menen, Belgium",
        "address": {"country": "Belgium", "city": "Menen"},
        "class": "leisure",
        "type": "sports_centre"
    },
    "Quelderduijn": {
        "lat": "52.94508140858851",
        "lon": "4.766940000403901",
        "display_name": "Sporthal De Quelderduijn, Katwijk, Netherlands",
        "address": {"country": "Netherlands", "city": "Katwijk"},
        "class": "leisure",
        "type": "sports_centre"
    },
    "SPORTCENTRUM DE KOEKOEK": {
        "lat": "52.28640008800095",
        "lon": "5.958627926328661",
        "display_name": "Sportcentrum De Koekoek, Erpe-Mere, Belgium",
        "address": {"country": "Belgium", "city": "Erpe-Mere"},
        "class": "leisure",
        "type": "sports_centre"
    }
}

# Hints for geocoding
HINTS: Dict[str, str] = {
    "Bosuilstadion": "Bosuilstadion, Antwerp, Belgium",
    "Dender Football Complex": "Dender Football Complex, Denderleeuw, Belgium",
    "Elindus Arena": "Elindus Arena, Waregem, Belgium",
    "Lotto Park": "Lotto Park, Anderlecht, Belgium",
    "King Power at Den Dreef Stadion": "Den Dreef, Leuven, Belgium",
    "King Power at Den Dreef Stadium": "Den Dreef, Leuven, Belgium",
    "Jan Breydelstadion": "Jan Breydelstadion, Bruges, Belgium",
    "Daio Wasabi Stayen Stadium": "Stayen, Sint-Truiden, Belgium",
    "AFAS Stadion": "AFAS Stadion, Mechelen, Belgium",
    "Het Kuipje": "Het Kuipje, Westerlo, Belgium",
    "Stade Maurice Dufrasne": "Stade Maurice Dufrasne, Liège, Belgium",
    "Cegeka Arena": "Cegeka Arena, Genk, Belgium",
    "Stade Joseph Marien": "Stade Joseph Marien, Forest, Brussels, Belgium",
    "Stade du Pays de Charleroi": "Stade du Pays de Charleroi, Charleroi, Belgium",
    "Maaspoort Sports & Events": "Maaspoort, 's-Hertogenbosch, Netherlands",
    "COREtec Dôme": "COREtec Dôme, Ostend, Belgium",
    "Sportcampus Lange Munte": "Sportcampus Lange Munte, Kortrijk, Belgium",
    "Sporthal Boshoven": "Sporthal Boshoven, Weert, Netherlands",
    "mons.arena": "Mons.Arena, Mons, Belgium",
    "Dôme": "Dôme, Charleroi, Belgium",
    "Topsportcentrum Rotterdam": "Topsportcentrum Rotterdam, Netherlands",
    "Complexe Sportif Neder-Over-Heembeek": "Neder-Over-Heembeek sports complex, Brussels, Belgium",
    "Lotto Arena": "Lotto Arena, Antwerp, Belgium",
    "Sporthal Alverberg": "Sporthal Alverberg, Hasselt, Belgium",
    "Quelderduijn": "Sporthal De Quelderduijn, Katwijk, Netherlands",
    "MartiniPlaza": "MartiniPlaza, Groningen, Netherlands",
    "Sporthal 1574": "Sporthal 1574, Leiden, Netherlands",
    "Kalverdijkje": "Kalverdijkje, Leeuwarden, Netherlands",
    "Winketkaai": "Winketkaai, Mechelen, Belgium",
    "Landstede Sportcentrum": "Landstede Sportcentrum, Zwolle, Netherlands",
    "ING Arena": "ING Arena (Palais 12), Brussels Expo, Belgium",
    "STEENGOED ARENA": "STEENGOED Arena, Maaseik, Belgium",
    "EDUGO Arena": "EDUGO Arena, Oostakker, Ghent, Belgium",
    "REO ARENA": "REO Arena, Roeselare, Belgium",
    "CENTRE SPORTIF J.MOISSE": "Centre Sportif J. Moisse, Belgium",
    "SPORTCENTRUM SCHOTTE": "Sportcentrum Schotte, Aalst, Belgium",
    "SPORTCENTRUM DE KOEKOEK": "Sportcentrum De Koekoek, Erpe-Mere, Belgium",
    "POLE-BALLON DE LA PROVINCE DE LIEGE": "Pôle Ballon de la Province de Liège, Belgium",
    "CC DE STEIGER VAUBAN": "CC De Steiger Vauban, Menen, Belgium",
    "Sporthal Arena": "Sporthal Arena, Belgium",
    "St Antonius Global Catering Arena": "Sint-Antonius Arena, Belgium",
    "Sporthal Diepvenneke": "Sporthal Diepvenneke, Belgium",
    "Sportcentrum Sint-Gillis": "Sportcentrum Sint-Gillis, Belgium",
    "Sporthal AVERBO": "Sporthal Averbo, Belgium",
    "Shape N Go Arena": "Shape N Go Arena, Belgium",
    "Sporthal AXION": "Sporthal Axion, Belgium",
    "Topsporthal Meerminnen": "Topsporthal De Meerminnen, Beveren, Belgium",
    "Salle Ballens ASBL": "Salle Ballens, Belgium",
    "The Farm (SV Zulte Waregem trainingscomplexi)": "The Farm training complex, Zulte, Belgium",
    "RSCA Belfius Academy (Neerpede)": "RSCA Belfius Academy, Neerpede, Anderlecht, Belgium",
    "Chillax Arena (PGB-stadion)": "Chillax Arena (PGB-stadion), Oostakker, Ghent, Belgium",
    "KRC Genk Jeugdcomplex": "KRC Genk Jeugdcomplex, Genk, Belgium",
    "The Stadium Roeselare (Schiervelde)": "Schiervelde (The Stadium), Roeselare, Belgium",
    "Jeugdcomplex KVC Westerlo ('t Kuipje kompleksinin yanında)": "KVC Westerlo Jeugdcomplex, Westerlo, Belgium",
    "SL16 Football Campus (Académie RLD)": "SL16 Football Campus, Rocourt, Liège, Belgium",
}

# Global venue cache
VENUE_CACHE = {}

def get_venue_coordinates(venue_name: str) -> tuple:
    """Venue için koordinatları al (cache + manuel + Nominatim API)"""
    if not venue_name:
        return None, None
    
    # Cache kontrolü
    if venue_name in VENUE_CACHE:
        return VENUE_CACHE[venue_name]
    
    # Önce manuel koordinatlara bak
    manual_key = None
    if venue_name in MANUAL_COORDINATES:
        manual_key = venue_name
    else:
        # Kısmi eşleşme kontrolü
        for key in MANUAL_COORDINATES.keys():
            if "kvc" in venue_name.lower() and "westerlo" in venue_name.lower() and "kvc" in key.lower() and "westerlo" in key.lower():
                manual_key = key
                break
            elif "kvc" not in venue_name.lower():
                name_words = set(venue_name.lower().split())
                key_words = set(key.lower().split())
                if len(key_words.intersection(name_words)) >= max(1, len(key_words) // 2):
                    manual_key = key
                    break
    
    if manual_key:
        manual_data = MANUAL_COORDINATES[manual_key]
        coords = (manual_data["lat"], manual_data["lon"])
        VENUE_CACHE[venue_name] = coords
        return coords
    
    # Nominatim API'ye sor
    try:
        q = HINTS.get(venue_name, f"{venue_name}, Belgium")
        params = {
            "q": q,
            "format": "jsonv2",
            "addressdetails": 1,
            "namedetails": 0,
            "limit": 3,
            "countrycodes": "be,nl",
            "viewbox": VIEWBOX,
            "bounded": 0,
        }
        
        time.sleep(1.1)  # Rate limit
        r = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=25)
        r.raise_for_status()
        data = r.json()
        
        if data:
            # En uygun sonucu seç
            def score(item):
                cl = item.get("class")
                tp = item.get("type")
                pri = 0
                if cl == "leisure": pri += 3
                if cl == "amenity": pri += 2
                if cl == "building": pri += 1
                if tp in {"stadium", "sports_centre", "arena", "sport_centre"}:
                    pri += 3
                if tp in {"school", "college", "university"}:
                    pri -= 1
                disp = item.get("display_name", "")
                if "Belgium" in disp or "België" in disp or "Belgie" in disp:
                    pri += 1
                if "Netherlands" in disp or "Nederland" in disp:
                    pri += 1
                return pri
            
            data.sort(key=score, reverse=True)
            coords = (data[0].get("lat"), data[0].get("lon"))
            VENUE_CACHE[venue_name] = coords
            return coords
        
    except Exception as e:
        print(f"⚠️ Geocoding hatası {venue_name}: {e}")
    
    # Cache'e None ekle ki tekrar denemesin
    VENUE_CACHE[venue_name] = (None, None)
    return None, None

def get_jpl_data():
    """Pro League JPL verilerini al"""
    print("📊 Pro League JPL verileri alınıyor...")
    try:
        # Tüm haftaları al (1-40 arası makul bir aralık)
        weeks = list(range(1, 41))
        matches = asyncio.run(get_jpl_matches(weeks, locale="nl"))
        
        # DataFrame'e çevir
        df = pd.DataFrame(matches)
        if not df.empty:
            df['lig'] = 'Pro League JPL'
            df['spor'] = 'Futbol'
        return df
    except Exception as e:
        print(f"❌ Pro League JPL hatası: {e}")
        return pd.DataFrame()

def get_bnxt_data():
    """BNXT League verilerini al"""
    print("🏀 BNXT League verileri alınıyor...")
    try:
        matches = get_bnxt_matches(season=2026, clubs=("BE","NL"), month=-1, lang="en", local_tz="Europe/Brussels")
        
        # DataFrame'e çevir
        df = pd.DataFrame(matches)
        if not df.empty:
            df['lig'] = 'BNXT League'
            df['spor'] = 'Basketbol'
        return df
    except Exception as e:
        print(f"❌ BNXT League hatası: {e}")
        return pd.DataFrame()

def get_volley_data():
    """Volley League verilerini al"""
    print("🏐 Volley League verileri alınıyor...")
    try:
        # Erkek maçları
        men_matches_raw = get_volley_matches("men")
        men_matches = normalize_matches(men_matches_raw)
        for match in men_matches:
            match["competition"] = "LOTTO VOLLEY LEAGUE MEN"
        
        # Kadın maçları
        women_matches_raw = get_volley_matches("women")
        women_matches = normalize_matches(women_matches_raw)
        for match in women_matches:
            match["competition"] = "BELGIAN VOLLEY LEAGUE WOMEN"
        
        # Birleştir
        all_matches = men_matches + women_matches
        
        # DataFrame'e çevir
        df = pd.DataFrame(all_matches)
        if not df.empty:
            df['lig'] = df['competition']
            df['spor'] = 'Voleybol'
        return df
    except Exception as e:
        print(f"❌ Volley League hatası: {e}")
        return pd.DataFrame()

def get_super_league_data():
    """Super League verilerini al"""
    print("⚽ Super League verileri alınıyor...")
    try:
        # Tüm haftaları al (1-20 arası makul bir aralık)
        weeks = list(range(1, 21))
        matches = asyncio.run(get_super_league_matches(weeks, locale="nl"))
        
        # DataFrame'e çevir
        df = pd.DataFrame(matches)
        if not df.empty:
            df['lig'] = 'Lotto Super League'
            df['spor'] = 'Kadın Futbol'
        return df
    except Exception as e:
        print(f"❌ Super League hatası: {e}")
        return pd.DataFrame()

def create_excel_file():
    """Tüm verileri tek Excel sheet'inde birleştir ve koordinatları ekle"""
    print("🚀 Tüm scraper verileri birleştiriliyor...")
    
    # Verileri al
    jpl_df = get_jpl_data()
    bnxt_df = get_bnxt_data()
    volley_df = get_volley_data()
    super_league_df = get_super_league_data()
    
    # Tüm verileri birleştir
    all_dataframes = []
    for df, name in [(jpl_df, 'Pro League JPL'), (bnxt_df, 'BNXT League'), 
                    (volley_df, 'Volley League'), (super_league_df, 'Super League')]:
        if not df.empty:
            all_dataframes.append(df)
    
    if not all_dataframes:
        print("❌ Hiç veri bulunamadı!")
        return None
    
    combined_df = pd.concat(all_dataframes, ignore_index=True)
    
    # OPTİMİZASYON: Benzersiz venue'ları bul ve sadece onlar için koordinat al
    print("🔍 Benzersiz venue'lar bulunuyor...")
    unique_venues = combined_df['venue'].dropna().unique()
    print(f"📊 Toplam {len(combined_df)} maç, {len(unique_venues)} benzersiz venue")
    
    # Venue koordinat cache'i
    venue_coords = {}
    
    # Önce manuel koordinatlarla eşleştir
    print("🎯 Manuel koordinatlarla eşleştiriliyor...")
    manual_matched = 0
    for venue in unique_venues:
        if venue in MANUAL_COORDINATES:
            manual_data = MANUAL_COORDINATES[venue]
            venue_coords[venue] = (manual_data["lat"], manual_data["lon"])
            manual_matched += 1
        else:
            # Kısmi eşleşme kontrolü
            for key in MANUAL_COORDINATES.keys():
                if "kvc" in venue.lower() and "westerlo" in venue.lower() and "kvc" in key.lower() and "westerlo" in key.lower():
                    manual_data = MANUAL_COORDINATES[key]
                    venue_coords[venue] = (manual_data["lat"], manual_data["lon"])
                    manual_matched += 1
                    break
                elif "kvc" not in venue.lower():
                    name_words = set(venue.lower().split())
                    key_words = set(key.lower().split())
                    if len(key_words.intersection(name_words)) >= max(1, len(key_words) // 2):
                        manual_data = MANUAL_COORDINATES[key]
                        venue_coords[venue] = (manual_data["lat"], manual_data["lon"])
                        manual_matched += 1
                        break
    
    print(f"✅ {manual_matched}/{len(unique_venues)} venue manuel koordinatlarla eşleştirildi")
    
    # Kalan venue'lar için API çağrısı yap
    remaining_venues = [v for v in unique_venues if v not in venue_coords]
    print(f"🌍 {len(remaining_venues)} venue için API çağrısı yapılıyor...")
    
    for i, venue in enumerate(remaining_venues):
        lat, lon = get_venue_coordinates(venue)
        venue_coords[venue] = (lat, lon)
        
        if (i + 1) % 5 == 0:  # Her 5 venue'da bir progress göster
            print(f"📍 {i + 1}/{len(remaining_venues)} venue işlendi...")
    
    # Koordinatları maçlara eşle
    print("🔗 Koordinatlar maçlara eşleniyor...")
    latitudes = []
    longitudes = []
    
    for venue in combined_df['venue']:
        if venue in venue_coords:
            lat, lon = venue_coords[venue]
            latitudes.append(lat)
            longitudes.append(lon)
        else:
            latitudes.append(None)
            longitudes.append(None)
    
    combined_df['latitude'] = latitudes
    combined_df['longitude'] = longitudes
    
    # Kolonları standartlaştır ve birleştir
    print("🔧 Kolonlar standartlaştırılıyor...")
    
    # week kolonunu numeric yap
    combined_df['week'] = pd.to_numeric(combined_df['week'], errors='coerce')
    
    # lig, spor, leg kolonlarını birleştir
    def create_season_info(row):
        parts = []
        
        # Lig bilgisi
        if pd.notna(row.get('lig')):
            parts.append(str(row['lig']))
        
        # Spor bilgisi
        if pd.notna(row.get('spor')):
            parts.append(str(row['spor']))
        
        # Leg bilgisi (varsa)
        if pd.notna(row.get('leg')):
            parts.append(str(row['leg']))
        
        # Week bilgisi (varsa)
        if pd.notna(row.get('week')):
            parts.append(f"Hafta {int(row['week'])}")
        
        return " | ".join(parts) if parts else None
    
    combined_df['season_info'] = combined_df.apply(create_season_info, axis=1)
    
    # Excel dosyası oluştur
    excel_file = "out/tum_ligler_tek_sheet.xlsx"
    Path("out").mkdir(exist_ok=True)
    
    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        # Kolon sıralamasını düzenle
        column_order = [
            'match_name', 'date_local', 'time_local', 'date_utc', 'time_utc',
            'venue', 'venue_city', 'latitude', 'longitude', 'competition', 
            'season_info', 'week'
        ]
        
        # Sadece mevcut kolonları al ve sırala
        available_columns = [col for col in column_order if col in combined_df.columns]
        final_df = combined_df[available_columns].copy()
        
        # Sayısal kolonları numeric yap
        if 'week' in final_df.columns:
            final_df['week'] = pd.to_numeric(final_df['week'], errors='coerce')
        if 'latitude' in final_df.columns:
            final_df['latitude'] = pd.to_numeric(final_df['latitude'], errors='coerce')
        if 'longitude' in final_df.columns:
            final_df['longitude'] = pd.to_numeric(final_df['longitude'], errors='coerce')
        
        final_df.to_excel(writer, sheet_name='Tüm Maçlar', index=False)
    
    print(f"\n🎉 Excel dosyası oluşturuldu: {excel_file}")
    print(f"📊 Toplam {len(combined_df)} maç")
    
    # Koordinat istatistikleri
    coord_count = combined_df['latitude'].notna().sum()
    print(f"📍 {coord_count}/{len(combined_df)} maç için koordinat bulundu")
    print(f"🎯 {len(unique_venues)} benzersiz venue'dan {len([v for v in VENUE_CACHE.values() if v[0] is not None])} tanesi için koordinat alındı")
    
    return excel_file

def main():
    """Ana fonksiyon"""
    print("=" * 60)
    print("🏆 TÜM LİGLER VERİLERİ EXCEL'E AKTARILIYOR")
    print("🌍 LATITUDE/LONGITUDE KOORDİNATLARI İLE")
    print("=" * 60)
    
    try:
        excel_file = create_excel_file()
        
        if not excel_file:
            print("❌ Excel dosyası oluşturulamadı!")
            sys.exit(1)
        
        print("\n" + "=" * 60)
        print("📋 ÖZET:")
        print("=" * 60)
        
        # Dosya boyutunu göster
        file_size = Path(excel_file).stat().st_size
        print(f"📁 Dosya: {excel_file}")
        print(f"📏 Boyut: {file_size:,} bytes ({file_size/1024:.1f} KB)")
        
        print("\n🎯 Özellikler:")
        print("- ✅ Tek sheet'te tüm maçlar")
        print("- ✅ Latitude/Longitude koordinatları")
        print("- ✅ Hem Belgium hem UTC saatleri")
        print("- ✅ Standart format: match_name, date_local, time_local, date_utc, time_utc, venue, latitude, longitude, competition, week")
        
        print("\n📊 Kolonlar:")
        print("- match_name: Ev Sahibi vs Deplasman")
        print("- date_local/time_local: Belgium saatleri")
        print("- date_utc/time_utc: UTC saatleri")
        print("- venue: Stadyum/Salon adı")
        print("- venue_city: Şehir (varsa)")
        print("- latitude/longitude: GPS koordinatları (numeric)")
        print("- competition: Lig adı")
        print("- season_info: Lig | Spor | Leg | Hafta (birleştirilmiş)")
        print("- week: Hafta numarası (numeric)")
        
    except Exception as e:
        print(f"❌ Hata: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
