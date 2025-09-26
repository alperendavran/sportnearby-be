#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph Nodes - Her node tek iş yapar
"""

from datetime import date
from typing import Dict, Any

from .graph_state import AgentState
from .tools import (
    classify_intent_tool, normalize_dates_tool, extract_cities_tool,
    geocode_text_tool, db_find_near_tool, db_list_competitions_tool,
    db_competition_ids_tool, db_venue_ids_tool
)


async def n_classify(state: AgentState) -> AgentState:
    """Intent classification node"""
    state.add_step("classify_intent")
    
    # Handle empty or very short queries
    if not state.q or len(state.q.strip()) < 2:
        state.error = "CLASSIFY_ERROR"
        state.error_message = "Query not understood, please use a clearer expression."
        state.add_step("ERROR: CLASSIFY_ERROR - Empty or too short query")
        return state
    
    try:
        dec = await classify_intent_tool.ainvoke(state.q)
        state.intent = dec["intent"]
        state.slots = dec["slots"] or {}
        
        # Handle unclear queries
        if state.intent == "unclear_query":
            state.error = "UNCLEAR_QUERY"
            state.error_message = "I didn't understand your request. Please ask about sports events, competitions, or venues in Belgium."
            state.add_step("ERROR: UNCLEAR_QUERY - Random or unclear text")
            return state
        
        # Radius default'u
        if state.slots.get("radius_km"):
            state.radius_km = float(state.slots["radius_km"])
        
        state.add_step(f"intent_classified: {state.intent}")
        
    except Exception as e:
        state.set_error("CLASSIFY_ERROR", f"Intent classification failed: {str(e)}")
    
    return state


async def n_dates(state: AgentState) -> AgentState:
    """Date resolution node"""
    state.add_step("resolve_dates")
    
    # list_competitions hariç hepsi için tarih çözümle
    if state.intent == "list_competitions":
        state.add_step("dates_skipped: list_competitions")
        return state
    
    try:
        dr = await normalize_dates_tool.ainvoke(state.q)
        state.date_status = dr["status"]
        
        if dr["status"] == "OK":
            state.date_from = dr["date_from"]
            state.date_to = dr["date_to"]
            # Store time_keyword for evaluation
            state.time_keyword = dr.get("time_keyword")
            state.add_step(f"dates_resolved: {state.date_from} to {state.date_to} (keyword: {state.time_keyword})")
            
        elif dr["status"] == "NO_TIME":
            # Varsayılan bugün
            today = date.today().isoformat()
            state.date_from, state.date_to = today, today
            state.add_step(f"dates_default: {today}")
            
        else:  # UNCLEAR
            # Fallback: Show next 10 days for unclear time expressions
            today = date.today()
            from datetime import timedelta
            state.date_from = today.isoformat()
            state.date_to = (today + timedelta(days=10)).isoformat()
            state.add_step(f"dates_fallback_10days: {state.date_from} to {state.date_to}")
            state.add_step("unclear_time_fallback: Showing next 10 days")
            
    except Exception as e:
        state.set_error("DATE_ERROR", f"Date resolution failed: {str(e)}")
    
    return state


async def n_location(state: AgentState) -> AgentState:
    """Location resolution node"""
    state.add_step("resolve_location")
    
    # list_competitions için konum gerekmez
    if state.intent == "list_competitions":
        state.add_step("location_skipped: list_competitions")
        return state
    
    try:
        coords = []
        
        # 1. User-provided coordinates
        if state.user_lat is not None and state.user_lon is not None:
            coords.append({"lat": state.user_lat, "lon": state.user_lon})
            state.add_step("location_from_user_coords")
        
        # 2. Slot'lardaki şehirler
        cities = state.slots.get("cities") or []
        if cities and not coords:
            for city in cities:
                try:
                    g = await geocode_text_tool.ainvoke(city)
                    if g["status"] == "OK" and g["lat"] and g["lon"]:
                        coords.append({"lat": g["lat"], "lon": g["lon"]})
                        state.add_step(f"location_from_city: {city}")
                except Exception:
                    continue
        
        # 3. Fallback: tüm cümleyi geocode et
        if not coords:
            try:
                g = await geocode_text_tool.ainvoke(state.q)
                if g["status"] == "OK" and g["lat"] and g["lon"]:
                    coords.append({"lat": g["lat"], "lon": g["lon"]})
                    state.add_step("location_from_query")
            except Exception:
                pass
        
        state.coords = coords
        
        if not coords:
            state.set_error("NO_LOCATION", "Location not specified. Please add a city name (e.g., 'Brussels sports activities') or share your coordinates.")
        else:
            state.add_step(f"location_resolved: {len(coords)} coordinates")
            
    except Exception as e:
        state.set_error("LOCATION_ERROR", f"Location resolution failed: {str(e)}")
    
    return state


async def n_search(state: AgentState) -> AgentState:
    """Search node"""
    state.add_step("search_events")
    
    try:
        # list_competitions için özel işlem
        if state.intent == "list_competitions":
            state.results = await db_list_competitions_tool.ainvoke("")
            state.add_step("search_competitions_completed")
            return state
        
        # Hata varsa arama yapma
        if state.has_error():
            state.add_step("search_skipped: has_error")
            return state
        
        # Competition ve venue ID'lerini çöz
        comp_ids = []
        ven_ids = []
        
        if state.slots.get("competitions"):
            comp_ids = await db_competition_ids_tool.ainvoke({"names": state.slots["competitions"]})
            state.add_step(f"competition_ids_resolved: {len(comp_ids)}")
        
        if state.slots.get("venues"):
            ven_ids = await db_venue_ids_tool.ainvoke({"names": state.slots["venues"]})
            state.add_step(f"venue_ids_resolved: {len(ven_ids)}")
        
        # Her koordinat için arama yap
        all_rows = []
        search_coords = state.get_coords_for_search()
        
        for coord in search_coords[:5]:  # Max 5 coordinates
            try:
                rows = await db_find_near_tool.ainvoke({
                    "lat": coord["lat"],
                    "lon": coord["lon"],
                    "radius_km": state.radius_km,
                    "date_from": state.date_from,
                    "date_to": state.date_to,
                    "competition_ids": comp_ids or None,
                    "venue_ids": ven_ids or None,
                    "limit": 50,
                    "sort": state.slots.get("sort") or "distance"
                })
                all_rows.extend(rows)
                state.add_step(f"search_coord: {coord['lat']:.3f},{coord['lon']:.3f} -> {len(rows)} results")
            except Exception as e:
                state.add_step(f"search_coord_error: {str(e)}")
                continue
        
        # Dedupe by id, keep min distance
        best = {}
        for row in all_rows:
            rid = row["id"]
            if rid not in best or row["distance_km"] < best[rid]["distance_km"]:
                best[rid] = row
        
        state.results = list(best.values())
        state.add_step(f"search_completed: {len(state.results)} unique results")
        
    except Exception as e:
        state.set_error("SEARCH_ERROR", f"Search failed: {str(e)}")
    
    return state


async def n_post(state: AgentState) -> AgentState:
    """Post-processing node"""
    state.add_step("post_process")
    
    try:
        # list_competitions için post-processing gerekmez
        if state.intent == "list_competitions":
            state.add_step("post_skipped: list_competitions")
            return state
        
        # Sort + limit
        sort = state.slots.get("sort") or "distance"
        limit = state.slots.get("limit") or state.limit
        
        if sort == "time":
            state.results = sorted(state.results, key=lambda x: x["datetime_local"])
        else:  # distance
            state.results = sorted(state.results, key=lambda x: x["distance_km"])
        
        state.results = state.results[:limit]
        state.add_step(f"post_completed: {len(state.results)} final results")
        
    except Exception as e:
        state.set_error("POST_ERROR", f"Post-processing failed: {str(e)}")
    
    return state


async def n_error_handler(state: AgentState) -> AgentState:
    """Error handling node"""
    state.add_step("handle_error")
    
    if state.error == "UNCLEAR_TIME":
        state.error_message = "Date expression is unclear, please specify a clearer date."
    elif state.error == "NO_LOCATION":
        state.error_message = "Location not specified, please add a city name or share your coordinates."
    elif state.error == "CLASSIFY_ERROR":
        state.error_message = "Query not understood, please use a clearer expression."
    elif state.error == "UNCLEAR_QUERY":
        state.error_message = "I didn't understand your request. Please ask about sports events, competitions, or venues in Belgium."
    elif state.error == "SEARCH_ERROR":
        state.error_message = "Error occurred during search."
    else:
        state.error_message = f"Unexpected error: {state.error}"
    
    state.add_step(f"error_handled: {state.error}")
    return state
