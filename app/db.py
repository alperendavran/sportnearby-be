#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database connection pool and repository functions
"""

import asyncpg
from typing import List, Optional, Tuple
from datetime import date
from .settings import settings
from .models import MatchOut


# Global connection pool
pool: Optional[asyncpg.Pool] = None


async def create_pool():
    """Create database connection pool"""
    global pool
    pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=1,
        max_size=10
    )


async def close_pool():
    """Close database connection pool"""
    global pool
    if pool:
        await pool.close()


async def get_db_connection():
    """Get database connection from pool"""
    if pool:
        return await pool.acquire()
    return await asyncpg.connect(dsn=settings.database_url)


async def competition_ids_by_names(names: List[str]) -> List[int]:
    """Competition isimlerinden ID'leri getir - SQL injection korumalı"""
    if not names:
        return []
    
    # SQL injection koruması - sadece alfanumerik karakterler
    safe_names = [name.strip() for name in names if name and name.strip().replace(' ', '').replace('-', '').isalnum()]
    if not safe_names:
        return []
    
    placeholders = ','.join([f'${i+1}' for i in range(len(safe_names))])
    query = f"""
        SELECT id FROM competitions 
        WHERE LOWER(name) = ANY(ARRAY[{placeholders}])
    """
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *[name.lower() for name in safe_names])
        return [row['id'] for row in rows]


async def venue_ids_by_names(names: List[str]) -> List[int]:
    """Venue isimlerinden ID'leri getir - SQL injection korumalı"""
    if not names:
        return []
    
    # SQL injection koruması - sadece alfanumerik karakterler
    safe_names = [name.strip() for name in names if name and name.strip().replace(' ', '').replace('-', '').isalnum()]
    if not safe_names:
        return []
    
    placeholders = ','.join([f'${i+1}' for i in range(len(safe_names))])
    query = f"""
        SELECT id FROM venues 
        WHERE LOWER(name) = ANY(ARRAY[{placeholders}])
    """
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *[name.lower() for name in safe_names])
        return [row['id'] for row in rows]


async def find_events_near_db(
    lat: float, 
    lon: float, 
    radius_km: float = 25.0,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    competition_ids: Optional[List[int]] = None,
    venue_ids: Optional[List[int]] = None,
    limit: int = 20
) -> List[MatchOut]:
    """Find events near coordinates with filters"""
    
    # Base query
    query = """
        SELECT 
            e.id,
            e.match_name,
            e.datetime_local,
            e.week,
            e.competition_id,
            c.name as competition,
            e.venue_id,
            v.name as venue,
            v.city,
            v.country,
            v.latitude,
            v.longitude,
            v.geom,
            ST_Distance(
                v.geom::geography, 
                ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography
            ) / 1000.0 as distance_km
        FROM events e
        JOIN venues v ON e.venue_id = v.id
        JOIN competitions c ON e.competition_id = c.id
        WHERE ST_DWithin(
            v.geom::geography, 
            ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography, 
            $3 * 1000
        )
    """
    
    params = [lat, lon, radius_km]
    param_count = 3
    
    # Add date filters
    if date_from:
        param_count += 1
        query += f" AND e.datetime_local::date >= ${param_count}"
        params.append(date.fromisoformat(date_from))
    
    if date_to:
        param_count += 1
        query += f" AND e.datetime_local::date <= ${param_count}"
        params.append(date.fromisoformat(date_to))
    
    # Add competition filter
    if competition_ids:
        param_count += 1
        placeholders = ','.join([f'${i}' for i in range(param_count + 1, param_count + 1 + len(competition_ids))])
        query += f" AND e.competition_id = ANY(ARRAY[{placeholders}])"
        params.extend(competition_ids)
        param_count += len(competition_ids)
    
    # Add venue filter
    if venue_ids:
        param_count += 1
        placeholders = ','.join([f'${i}' for i in range(param_count + 1, param_count + 1 + len(venue_ids))])
        query += f" AND e.venue_id = ANY(ARRAY[{placeholders}])"
        params.extend(venue_ids)
        param_count += len(venue_ids)
    
    # Order and limit
    query += " ORDER BY distance_km ASC LIMIT $" + str(param_count + 1)
    params.append(limit)
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        # Convert datetime objects to strings for Pydantic
        results = []
        for row in rows:
            row_dict = dict(row)
            if 'datetime_local' in row_dict and row_dict['datetime_local']:
                row_dict['datetime_local'] = row_dict['datetime_local'].isoformat()
            results.append(MatchOut(**row_dict))
        return results


async def next_events_at_venue_db(venue_id: int, limit: int = 5) -> List[MatchOut]:
    """Get next events at a specific venue"""
    query = """
        SELECT 
            e.id,
            e.match_name,
            e.datetime_local,
            e.week,
            e.competition_id,
            c.name as competition,
            e.venue_id,
            v.name as venue,
            v.city,
            v.country,
            v.latitude,
            v.longitude,
            v.geom,
            0.0 as distance_km
        FROM events e
        JOIN venues v ON e.venue_id = v.id
        JOIN competitions c ON e.competition_id = c.id
        WHERE e.venue_id = $1
        AND e.datetime_local > NOW()
        ORDER BY e.datetime_local ASC
        LIMIT $2
    """
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, venue_id, limit)
        # Convert datetime objects to strings for Pydantic
        results = []
        for row in rows:
            row_dict = dict(row)
            if 'datetime_local' in row_dict and row_dict['datetime_local']:
                row_dict['datetime_local'] = row_dict['datetime_local'].isoformat()
            results.append(MatchOut(**row_dict))
        return results


async def venues_near_db(lat: float, lon: float, radius_km: float = 25.0, limit: int = 10) -> List[dict]:
    """Find venues near coordinates"""
    query = """
        SELECT 
            v.id,
            v.name,
            v.city,
            v.country,
            v.latitude,
            v.longitude,
            ST_Distance(
                v.geom::geography, 
                ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography
            ) / 1000.0 as distance_km
        FROM venues v
        WHERE ST_DWithin(
            v.geom::geography, 
            ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography, 
            $3 * 1000
        )
        ORDER BY distance_km ASC
        LIMIT $4
    """
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, lat, lon, radius_km, limit)
        return [dict(row) for row in rows]


async def list_competitions_db() -> List[dict]:
    """List all competitions"""
    query = """
        SELECT id, name, season, country
        FROM competitions
        ORDER BY name
    """
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
        return [dict(row) for row in rows]
