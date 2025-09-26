#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI endpoints and controllers
"""

from typing import Optional, List
from fastapi import FastAPI, Query, HTTPException

from .services import (
    geocode_service, extract_cities_service, pipeline_geocode_cities_service,
    nearest_matches_service, agent_query_service
)
from .models import GeocodeOut, ExtractOut, PipelineGeocodeOut, MatchOut
from .graph import GRAPH
from .graph_state import AgentState


def register_routes(app: FastAPI):
    """Register all API routes"""
    
    @app.get("/health")
    async def health():
        """Health check endpoint"""
        return {"status": "healthy", "service": "AI Sports Events Agent"}

    @app.get("/geocode", response_model=GeocodeOut)
    async def geocode(q: str = Query(..., description="Geocode location")):
        """Geocode a location using Ollama"""
        return await geocode_service(q)

    @app.get("/extract-city", response_model=List[str])
    async def extract_city(q: str = Query(..., description="Extract cities from text")):
        """Extract city names from text"""
        result = await extract_cities_service(q)
        return [mention.normalized for mention in result.mentions if mention.type == "city"]

    @app.get("/pipeline/geocode-cities", response_model=PipelineGeocodeOut)
    async def pipeline_geocode_cities(
        cities: str = Query(..., description="Comma-separated city names or text with cities")
    ):
        """Extract and geocode multiple cities from text"""
        return await pipeline_geocode_cities_service(cities)

    @app.get("/nearest-matches", response_model=List[MatchOut])
    async def nearest_matches(
        lat: float = Query(..., description="Latitude"),
        lon: float = Query(..., description="Longitude"),
        radius_km: float = Query(25.0, description="Search radius in kilometers"),
        date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
        date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
        competition_ids: Optional[List[int]] = Query(None, description="Filter by competition IDs"),
        venue_ids: Optional[List[int]] = Query(None, description="Filter by venue IDs"),
        limit: int = Query(20, ge=1, le=100, description="Maximum number of results")
    ):
        """Find nearest sports events with filters"""
        return await nearest_matches_service(
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            date_from=date_from,
            date_to=date_to,
            competition_ids=competition_ids,
            venue_ids=venue_ids,
            limit=limit
        )

    @app.get("/agent/query")
    async def agent_query(
        q: str = Query(..., description="Doğal dil istek"),
        lat: Optional[float] = Query(None, description="Latitude"),
        lon: Optional[float] = Query(None, description="Longitude"),
        limit: int = Query(20, ge=1, le=100, description="Maximum number of results")
    ):
        """
        Doğal dil ile spor etkinlikleri sorgulama (LangGraph powered).
        
        Örnekler:
        - "Brussels spor etkinlikleri"
        - "Bu hafta sonu yakınımdaki maçlar"
        - "Yakınımdaki stadyumlar"
        - "Hangi ligler var?"
        """
        try:
            # Create initial state
            state = AgentState(
                q=q,
                user_lat=lat,
                user_lon=lon,
                limit=limit
            )
            
            # Run graph
            final_state_dict = await GRAPH.ainvoke(state)
            final_state = AgentState(**final_state_dict)
            
            # Handle errors
            if final_state.has_error():
                if final_state.error == "UNCLEAR_TIME":
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "message": "Tarih ifadesi belirsiz, lütfen daha net bir tarih belirtin.",
                            "suggestion": "Örnek: 'bu hafta sonu', 'yarın', 'gelecek hafta', '8 hafta içerisinde'",
                            "query": q,
                            "error": final_state.error,
                            "processing_steps": final_state.processing_steps
                        }
                    )
                elif final_state.error == "NO_LOCATION":
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "message": "Konum belirtilmedi, lütfen şehir adı ekleyin veya koordinatlarınızı paylaşın.",
                            "suggestion": "Örnek: 'Brussels spor aktiviteleri', 'Antwerp maçları', 'yakınımdaki etkinlikler'",
                            "query": q,
                            "error": final_state.error,
                            "processing_steps": final_state.processing_steps
                        }
                    )
                else:
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "message": final_state.error_message or f"Agent query hatası: {final_state.error}",
                            "query": q,
                            "error": final_state.error,
                            "processing_steps": final_state.processing_steps
                        }
                    )
            
            # Check if this was an unclear time fallback
            unclear_time_fallback = any("unclear_time_fallback" in step for step in final_state.processing_steps)
            
            # Return successful response
            response = {
                "intent": final_state.intent,
                "query": final_state.q,
                "count": len(final_state.results),
                "results": final_state.results,
                "filters": {
                    "cities": final_state.slots.get("cities", []),
                    "competitions": final_state.slots.get("competitions", []),
                    "venues": final_state.slots.get("venues", []),
                    "radius_km": final_state.radius_km,
                    "date_from": final_state.date_from,
                    "date_to": final_state.date_to,
                    "time_keyword": final_state.time_keyword
                },
                "processing_steps": final_state.processing_steps
            }
            
            # Add fallback message if unclear time was used
            if unclear_time_fallback:
                response["message"] = "Tarih ifadesi belirsiz olduğu için önümüzdeki 10 günlük etkinlikler gösteriliyor."
                response["fallback_info"] = {
                    "type": "unclear_time",
                    "fallback_period": "next_10_days",
                    "original_query": final_state.q
                }
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": f"Agent query hatası: {str(e)}",
                    "query": q
                }
            )
