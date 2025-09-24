#!/usr/bin/env python3
# -*- coding: utf-8-sig -*-
"""
Professional PostgreSQL + PostGIS Database Setup for Sports Events
Multiple tables with proper relationships and normalization
"""

import psycopg
from psycopg.rows import dict_row
import pandas as pd
from datetime import datetime
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "sports_events",
    "user": "alperendavran",
    "password": None  # macOS PostgreSQL default
}

@dataclass
class VenueData:
    name: str
    city: str
    latitude: float
    longitude: float
    country: str = "Belgium"

@dataclass
class CompetitionData:
    name: str
    season: str
    country: str = "Belgium"

@dataclass
class EventData:
    match_name: str
    venue_id: int
    competition_id: int
    datetime_local: datetime
    week: Optional[int] = None

class DatabaseManager:
    """Database işlemleri için Single Responsibility Principle"""
    
    def __init__(self, config: dict):
        self.config = config
        self.connection = None
    
    def connect(self):
        """Database bağlantısı kur"""
        try:
            self.connection = psycopg.connect(**self.config, row_factory=dict_row)
            print("✅ Database bağlantısı kuruldu")
            return True
        except Exception as e:
            print(f"❌ Database bağlantı hatası: {e}")
            return False
    
    def close(self):
        """Database bağlantısını kapat"""
        if self.connection:
            self.connection.close()
            print("🔌 Database bağlantısı kapatıldı")
    
    def execute_sql(self, sql: str, params: tuple = None):
        """SQL sorgusu çalıştır"""
        try:
            with self.connection.cursor() as cur:
                cur.execute(sql, params)
                if cur.description:  # SELECT sorgusu ise
                    return cur.fetchall()
                else:  # INSERT/UPDATE/DELETE sorgusu ise
                    self.connection.commit()
                    return cur.rowcount
        except Exception as e:
            print(f"❌ SQL hatası: {e}")
            self.connection.rollback()
            return None

class SchemaManager:
    """Database schema yönetimi için"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def create_extensions(self):
        """PostgreSQL eklentilerini kur"""
        sql = """
        -- PostGIS eklentisi
        CREATE EXTENSION IF NOT EXISTS postgis;
        CREATE EXTENSION IF NOT EXISTS postgis_topology;
        """
        
        result = self.db.execute_sql(sql)
        if result is not None:
            print("✅ PostgreSQL eklentileri kuruldu")
            return True
        return False
    
    def drop_all_tables(self):
        """Tüm tabloları sil (temiz başlangıç için)"""
        sql = """
        DROP TABLE IF EXISTS events CASCADE;
        DROP TABLE IF EXISTS venues CASCADE;
        DROP TABLE IF EXISTS competitions CASCADE;
        """
        
        result = self.db.execute_sql(sql)
        if result is not None:
            print("🗑️ Mevcut tablolar silindi")
            return True
        return False
    
    def create_venues_table(self):
        """Venues tablosunu oluştur"""
        sql = """
        CREATE TABLE venues (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            city TEXT NOT NULL,
            country TEXT DEFAULT 'Belgium',
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            geom GEOGRAPHY(POINT) GENERATED ALWAYS AS (
                ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
            ) STORED,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            -- Constraints
            CONSTRAINT venues_name_city_unique UNIQUE (name, city),
            CONSTRAINT venues_lat_check CHECK (latitude BETWEEN -90 AND 90),
            CONSTRAINT venues_lon_check CHECK (longitude BETWEEN -180 AND 180)
        );
        
        -- Indexes
        CREATE INDEX idx_venues_geom ON venues USING gist (geom);
        CREATE INDEX idx_venues_city ON venues (city);
        CREATE INDEX idx_venues_name ON venues (name);
        """
        
        result = self.db.execute_sql(sql)
        if result is not None:
            print("✅ Venues tablosu oluşturuldu")
            return True
        return False
    
    def create_competitions_table(self):
        """Competitions tablosunu oluştur"""
        sql = """
        CREATE TABLE competitions (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            season TEXT NOT NULL,
            country TEXT DEFAULT 'Belgium',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            -- Constraints
            CONSTRAINT competitions_name_season_unique UNIQUE (name, season)
        );
        
        -- Indexes
        CREATE INDEX idx_competitions_name ON competitions (name);
        CREATE INDEX idx_competitions_season ON competitions (season);
        """
        
        result = self.db.execute_sql(sql)
        if result is not None:
            print("✅ Competitions tablosu oluşturuldu")
            return True
        return False
    
    def create_events_table(self):
        """Events tablosunu oluştur"""
        sql = """
        CREATE TABLE events (
            id BIGSERIAL PRIMARY KEY,
            match_name TEXT NOT NULL,
            venue_id BIGINT NOT NULL REFERENCES venues(id) ON DELETE RESTRICT,
            competition_id BIGINT NOT NULL REFERENCES competitions(id) ON DELETE RESTRICT,
            datetime_local TIMESTAMPTZ NOT NULL,
            week INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            -- Constraints
            CONSTRAINT events_match_datetime_unique UNIQUE (match_name, datetime_local),
            CONSTRAINT events_week_check CHECK (week > 0)
        );
        
        -- Indexes
        CREATE INDEX idx_events_venue_id ON events (venue_id);
        CREATE INDEX idx_events_competition_id ON events (competition_id);
        CREATE INDEX idx_events_datetime ON events (datetime_local);
        CREATE INDEX idx_events_week ON events (week);
        CREATE INDEX idx_events_match_name ON events (match_name);
        """
        
        result = self.db.execute_sql(sql)
        if result is not None:
            print("✅ Events tablosu oluşturuldu")
            return True
        return False
    
    def create_all_tables(self):
        """Tüm tabloları oluştur"""
        if not self.create_extensions():
            return False
        
        if not self.drop_all_tables():
            return False
        
        if not self.create_venues_table():
            return False
        
        if not self.create_competitions_table():
            return False
        
        if not self.create_events_table():
            return False
        
        print("🏗️ Tüm tablolar başarıyla oluşturuldu")
        return True

class VenueRepository:
    """Venue verileri için Repository Pattern"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def insert_venue(self, venue: VenueData) -> Optional[int]:
        """Venue ekle ve ID'sini döndür"""
        sql = """
        INSERT INTO venues (name, city, country, latitude, longitude) 
        VALUES (%s, %s, %s, %s, %s) 
        ON CONFLICT (name, city) DO UPDATE SET
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            updated_at = CURRENT_TIMESTAMP
        RETURNING id;
        """
        
        try:
            with self.db.connection.cursor() as cur:
                cur.execute(sql, (venue.name, venue.city, venue.country, venue.latitude, venue.longitude))
                result = cur.fetchone()
                self.db.connection.commit()
                return result['id'] if result else None
        except Exception as e:
            print(f"❌ Venue ekleme hatası: {e}")
            return None
    
    def get_venue_by_name_city(self, name: str, city: str) -> Optional[int]:
        """Name ve city'ye göre venue ID'sini getir"""
        sql = "SELECT id FROM venues WHERE name = %s AND city = %s;"
        result = self.db.execute_sql(sql, (name, city))
        return result[0]['id'] if result else None

class CompetitionRepository:
    """Competition verileri için Repository Pattern"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def insert_competition(self, competition: CompetitionData) -> Optional[int]:
        """Competition ekle ve ID'sini döndür"""
        sql = """
        INSERT INTO competitions (name, season, country) 
        VALUES (%s, %s, %s) 
        ON CONFLICT (name, season) DO NOTHING
        RETURNING id;
        """
        
        try:
            with self.db.connection.cursor() as cur:
                cur.execute(sql, (competition.name, competition.season, competition.country))
                result = cur.fetchone()
                if not result:
                    # Already exists, get the ID
                    cur.execute("SELECT id FROM competitions WHERE name = %s AND season = %s", 
                              (competition.name, competition.season))
                    result = cur.fetchone()
                self.db.connection.commit()
                return result['id'] if result else None
        except Exception as e:
            print(f"❌ Competition ekleme hatası: {e}")
            return None

class EventRepository:
    """Event verileri için Repository Pattern"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def insert_events(self, events: List[EventData]) -> bool:
        """Event listesini ekle"""
        if not events:
            print("⚠️ Eklenecek event yok")
            return False
        
        sql = """
        INSERT INTO events (match_name, venue_id, competition_id, datetime_local, week) 
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (match_name, datetime_local) DO NOTHING;
        """
        
        try:
            with self.db.connection.cursor() as cur:
                event_tuples = [
                    (event.match_name, event.venue_id, event.competition_id, 
                     event.datetime_local, event.week)
                    for event in events
                ]
                cur.executemany(sql, event_tuples)
                self.db.connection.commit()
                print(f"✅ {len(events)} event eklendi")
                return True
        except Exception as e:
            print(f"❌ Event ekleme hatası: {e}")
            return False

class ExcelDataProcessor:
    """Excel verilerini işlemek için Single Responsibility"""
    
    def __init__(self, excel_file: str):
        self.excel_file = excel_file
        self.venues = {}  # name+city -> VenueData
        self.competitions = {}  # name+season -> CompetitionData
    
    def load_data(self) -> pd.DataFrame:
        """Excel dosyasından veri yükle"""
        try:
            df = pd.read_excel(self.excel_file, sheet_name='Tüm Maçlar')
            print(f"✅ Excel verisi yüklendi: {len(df)} satır")
            return df
        except Exception as e:
            print(f"❌ Excel yükleme hatası: {e}")
            return pd.DataFrame()
    
    def extract_venues(self, df: pd.DataFrame) -> List[VenueData]:
        """DataFrame'den unique venue'leri çıkar"""
        venues = []
        venue_set = set()
        
        for _, row in df.iterrows():
            venue_name = str(row.get('venue', '')).strip()
            venue_city = str(row.get('venue_city', '')).strip()
            lat = row.get('latitude')
            lon = row.get('longitude')
            
            # Boş veya geçersiz veriler
            if not venue_name or not venue_city or pd.isna(lat) or pd.isna(lon):
                continue
            
            venue_key = (venue_name, venue_city)
            if venue_key not in venue_set:
                venue_set.add(venue_key)
                venue_data = VenueData(
                    name=venue_name,
                    city=venue_city,
                    latitude=float(lat),
                    longitude=float(lon)
                )
                venues.append(venue_data)
                self.venues[venue_key] = venue_data
        
        print(f"✅ {len(venues)} unique venue çıkarıldı")
        return venues
    
    def extract_competitions(self, df: pd.DataFrame) -> List[CompetitionData]:
        """DataFrame'den unique competition'ları çıkar"""
        competitions = []
        competition_set = set()
        
        for _, row in df.iterrows():
            competition_name = str(row.get('competition', '')).strip()
            season_info = str(row.get('season_info', '')).strip()
            
            if not competition_name:
                continue
            
            # Season info'dan season çıkar
            season = season_info.split(' | ')[0] if ' | ' in season_info else season_info
            if not season:
                season = "2024-2025"  # Default season
            
            competition_key = (competition_name, season)
            if competition_key not in competition_set:
                competition_set.add(competition_key)
                comp_data = CompetitionData(
                    name=competition_name,
                    season=season
                )
                competitions.append(comp_data)
                self.competitions[competition_key] = comp_data
        
        print(f"✅ {len(competitions)} unique competition çıkarıldı")
        return competitions
    
    def process_events(self, df: pd.DataFrame, venue_repo: VenueRepository, 
                      competition_repo: CompetitionRepository) -> List[EventData]:
        """DataFrame'den event'leri işle"""
        events = []
        
        for _, row in df.iterrows():
            try:
                # Match name
                match_name = str(row.get('match_name', '')).strip()
                if not match_name:
                    continue
                
                # Venue ID
                venue_name = str(row.get('venue', '')).strip()
                venue_city = str(row.get('venue_city', '')).strip()
                venue_id = venue_repo.get_venue_by_name_city(venue_name, venue_city)
                if not venue_id:
                    print(f"⚠️ Venue bulunamadı: {venue_name}, {venue_city}")
                    continue
                
                # Competition ID
                competition_name = str(row.get('competition', '')).strip()
                season_info = str(row.get('season_info', '')).strip()
                season = season_info.split(' | ')[0] if ' | ' in season_info else season_info
                if not season:
                    season = "2024-2025"
                
                competition_key = (competition_name, season)
                if competition_key not in self.competitions:
                    print(f"⚠️ Competition bulunamadı: {competition_name}, {season}")
                    continue
                
                # Get competition ID from database
                competition_id = None
                sql = "SELECT id FROM competitions WHERE name = %s AND season = %s"
                result = venue_repo.db.execute_sql(sql, (competition_name, season))
                if result:
                    competition_id = result[0]['id']
                
                if not competition_id:
                    print(f"⚠️ Competition ID bulunamadı: {competition_name}, {season}")
                    continue
                
                # Datetime
                date_str = str(row['date_local'])
                time_str = str(row['time_local'])
                datetime_str = f"{date_str} {time_str}"
                
                try:
                    datetime_obj = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
                except ValueError:
                    datetime_obj = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
                
                # Europe/Brussels timezone
                from zoneinfo import ZoneInfo
                brussels_tz = ZoneInfo("Europe/Brussels")
                datetime_local = datetime_obj.replace(tzinfo=brussels_tz)
                
                # Week
                week = row.get('week')
                week = int(week) if pd.notna(week) else None
                
                event = EventData(
                    match_name=match_name,
                    venue_id=venue_id,
                    competition_id=competition_id,
                    datetime_local=datetime_local,
                    week=week
                )
                
                events.append(event)
                
            except Exception as e:
                print(f"⚠️ Event işleme hatası: {e}")
                continue
        
        print(f"✅ {len(events)} event işlendi")
        return events

def main():
    """Ana fonksiyon"""
    print("=" * 80)
    print("🏆 PROFESSIONAL POSTGRESQL + POSTGIS SPORTS EVENTS DATABASE")
    print("=" * 80)
    
    # Excel dosyası kontrolü
    excel_file = "tum_ligler_tek_sheet.xlsx"
    if not Path(excel_file).exists():
        print(f"❌ Excel dosyası bulunamadı: {excel_file}")
        return
    
    # Database bağlantısı
    db_manager = DatabaseManager(DB_CONFIG)
    if not db_manager.connect():
        return
    
    try:
        # Schema oluştur
        schema_manager = SchemaManager(db_manager)
        if not schema_manager.create_all_tables():
            return
        
        # Repositories
        venue_repo = VenueRepository(db_manager)
        competition_repo = CompetitionRepository(db_manager)
        event_repo = EventRepository(db_manager)
        
        # Excel verilerini işle
        processor = ExcelDataProcessor(excel_file)
        df = processor.load_data()
        
        if df.empty:
            return
        
        # 1. Venues ekle
        print("\n📍 VENUES İŞLENİYOR...")
        venues = processor.extract_venues(df)
        venue_ids = []
        for venue in venues:
            venue_id = venue_repo.insert_venue(venue)
            if venue_id:
                venue_ids.append(venue_id)
        
        print(f"✅ {len(venue_ids)} venue eklendi")
        
        # 2. Competitions ekle
        print("\n🏆 COMPETITIONS İŞLENİYOR...")
        competitions = processor.extract_competitions(df)
        competition_ids = []
        for competition in competitions:
            competition_id = competition_repo.insert_competition(competition)
            if competition_id:
                competition_ids.append(competition_id)
        
        print(f"✅ {len(competition_ids)} competition eklendi")
        
        # 3. Events ekle
        print("\n⚽ EVENTS İŞLENİYOR...")
        events = processor.process_events(df, venue_repo, competition_repo)
        if events:
            event_repo.insert_events(events)
        
        # Sonuçları göster
        print("\n" + "="*80)
        print("🎉 DATABASE SETUP TAMAMLANDI!")
        print("="*80)
        
        # İstatistikler
        stats_queries = [
            ("Venues", "SELECT COUNT(*) as count FROM venues"),
            ("Competitions", "SELECT COUNT(*) as count FROM competitions"),
            ("Events", "SELECT COUNT(*) as count FROM events"),
        ]
        
        for name, query in stats_queries:
            result = db_manager.execute_sql(query)
            if result:
                print(f"📊 {name}: {result[0]['count']}")
        
        # Test sorguları
        print("\n🔍 TEST SORGUSU:")
        test_sql = """
        SELECT 
            e.match_name,
            v.name as venue_name,
            v.city as venue_city,
            c.name as competition,
            c.season,
            e.datetime_local
        FROM events e
        JOIN venues v ON e.venue_id = v.id
        JOIN competitions c ON e.competition_id = c.id
        ORDER BY e.datetime_local
        LIMIT 5;
        """
        
        test_results = db_manager.execute_sql(test_sql)
        if test_results:
            print("Sample events:")
            for row in test_results:
                print(f"  • {row['match_name']} at {row['venue_name']}, {row['venue_city']}")
                print(f"    {row['competition']} ({row['season']}) - {row['datetime_local']}")
                print()
    
    finally:
        db_manager.close()

if __name__ == "__main__":
    main()
