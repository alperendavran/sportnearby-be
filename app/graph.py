#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph Graph Definition
"""

from langgraph.graph import StateGraph, END
from .graph_state import AgentState
from .nodes import n_classify, n_dates, n_location, n_search, n_post, n_error_handler


def should_continue_after_classify(state: AgentState) -> str:
    """Decide next step after intent classification"""
    if state.has_error():
        return "error_handler"
    if state.intent == "list_competitions":
        return "search"  # Skip dates and location
    return "dates"  # Normal flow


def should_continue_after_dates(state: AgentState) -> str:
    """Decide next step after date resolution"""
    if state.has_error():
        return "error_handler"
    return "location"


def should_continue_after_location(state: AgentState) -> str:
    """Decide next step after location resolution"""
    if state.has_error():
        return "error_handler"
    return "search"


def should_continue_after_search(state: AgentState) -> str:
    """Decide next step after search"""
    if state.has_error():
        return "error_handler"
    return "post"


def should_end_after_post(state: AgentState) -> str:
    """Decide if we should end after post-processing"""
    return "end"


def build_graph() -> StateGraph:
    """Build the LangGraph workflow"""
    
    # Create graph
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("classify", n_classify)
    graph.add_node("dates", n_dates)
    graph.add_node("location", n_location)
    graph.add_node("search", n_search)
    graph.add_node("post", n_post)
    graph.add_node("error_handler", n_error_handler)
    
    # Set entry point
    graph.set_entry_point("classify")
    
    # Add conditional edges
    graph.add_conditional_edges(
        "classify",
        should_continue_after_classify,
        {
            "dates": "dates",
            "search": "search",
            "error_handler": "error_handler"
        }
    )
    
    graph.add_conditional_edges(
        "dates",
        should_continue_after_dates,
        {
            "location": "location",
            "error_handler": "error_handler"
        }
    )
    
    graph.add_conditional_edges(
        "location",
        should_continue_after_location,
        {
            "search": "search",
            "error_handler": "error_handler"
        }
    )
    
    graph.add_conditional_edges(
        "search",
        should_continue_after_search,
        {
            "post": "post",
            "error_handler": "error_handler"
        }
    )
    
    graph.add_conditional_edges(
        "post",
        should_end_after_post,
        {
            "end": END
        }
    )
    
    # Error handler always ends
    graph.add_edge("error_handler", END)
    
    return graph.compile()


# Global graph instance
GRAPH = build_graph()
