#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph State Model
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AgentState(BaseModel):
    """Graph boyunca taşınan durum"""
    
    # Input
    q: str  # Original query
    user_lat: Optional[float] = None
    user_lon: Optional[float] = None
    limit: int = 20
    
    # Intent classification
    intent: Optional[str] = None
    slots: Dict[str, Any] = Field(default_factory=dict)
    
    # Date resolution
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    date_status: Optional[str] = None  # "OK", "NO_TIME", "UNCLEAR"
    
    # Location resolution
    coords: List[Dict[str, float]] = Field(default_factory=list)  # [{"lat":..,"lon":..}]
    radius_km: float = 25.0
    
    # Search results
    results: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Error handling
    error: Optional[str] = None
    error_message: Optional[str] = None
    
    # Metadata
    processing_steps: List[str] = Field(default_factory=list)
    
    def add_step(self, step: str):
        """Add processing step for debugging"""
        self.processing_steps.append(step)
    
    def set_error(self, error_type: str, message: str):
        """Set error state"""
        self.error = error_type
        self.error_message = message
        self.add_step(f"ERROR: {error_type} - {message}")
    
    def has_error(self) -> bool:
        """Check if state has error"""
        return self.error is not None
    
    def get_coords_for_search(self) -> List[Dict[str, float]]:
        """Get coordinates for search, with fallback to Brussels"""
        if self.coords:
            return self.coords
        
        # Fallback to Brussels if no coords
        return [{"lat": 50.8503, "lon": 4.3517}]
