from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_community.chat_models import ChatOllama
from .models import Filters
from datetime import datetime, timedelta
import json

parser = JsonOutputParser(pydantic_object=Filters)

SYSTEM = """Extract Belgian sports fixture filters from user queries. Return ONLY valid JSON.

Rules:
- Use Europe/Brussels calendar; prefer future dates
- "weekend" => weekday="Sat" (backend will expand to Sat+Sun)
- Competitions must be exactly one of: "Jupiler Pro League", "Lotto Super League", "BNXT League 2025 - 2026", "LOTTO VOLLEY LEAGUE MEN", "BELGIAN VOLLEY LEAGUE WOMEN"
- Do not invent lat/lon coordinates - only use if explicitly provided
- Default radius_km is 30 if location mentioned
- Convert relative dates: "next week" = date_from in 7 days, "this weekend" = next Sat-Sun
- Time format: HH:MM (24-hour)
- Date format: YYYY-MM-DD

Examples:
- "Genk matches" → {"team": "Genk"}
- "football games this weekend" → {"competition": "Jupiler Pro League", "weekday": "Sat"}
- "volleyball in Brussels" → {"competition": "LOTTO VOLLEY LEAGUE MEN", "city": "Brussels"}
- "matches near me" → {"radius_km": 30} (lat/lon from user_location)
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM),
    ("user", "User query: {q}\nUser location: {user_location}\nCurrent date: {current_date}\n{format_instructions}")
]).partial(format_instructions=parser.get_format_instructions())

# Ollama model - local LLM
llm = ChatOllama(model="llama3.1:8b", temperature=0)

chain = prompt | llm | parser

def extract_filters(query: str, user_location: dict = None) -> Filters:
    """
    Extract structured filters from natural language query using Ollama LLM
    
    Args:
        query: User's natural language query
        user_location: Optional dict with "lat" and "lon" keys
        
    Returns:
        Filters object with extracted parameters
    """
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # Prepare user location string
    location_str = "Not provided"
    if user_location and "lat" in user_location and "lon" in user_location:
        location_str = f"Lat: {user_location['lat']}, Lon: {user_location['lon']}"
    
    try:
        result = chain.invoke({
            "q": query,
            "user_location": location_str,
            "current_date": current_date
        })
        return result
    except Exception as e:
        print(f"❌ LLM extraction error: {e}")
        # Fallback to basic parsing
        return _fallback_parser(query, user_location)

def _fallback_parser(query: str, user_location: dict = None) -> Filters:
    """
    Simple fallback parser when LLM fails
    """
    query_lower = query.lower()
    filters = Filters()
    
    # Basic team detection
    teams = ["genk", "anderlecht", "brugge", "antwerp", "gent", "leuven", "westerlo"]
    for team in teams:
        if team in query_lower:
            filters.team = team.title()
            break
    
    # Competition detection
    if "football" in query_lower or "soccer" in query_lower:
        filters.competition = "Jupiler Pro League"
    elif "basketball" in query_lower:
        filters.competition = "BNXT League 2025 - 2026"
    elif "volleyball" in query_lower or "volley" in query_lower:
        filters.competition = "LOTTO VOLLEY LEAGUE MEN"
    elif "women" in query_lower and ("football" in query_lower or "soccer" in query_lower):
        filters.competition = "Lotto Super League"
    
    # Location detection
    if user_location and ("near" in query_lower or "close" in query_lower):
        filters.lat = user_location.get("lat")
        filters.lon = user_location.get("lon")
        filters.radius_km = 30
    
    return filters

def test_extractor():
    """Test the extractor with sample queries"""
    test_queries = [
        "Genk maçları bu hafta sonu",
        "Football games in Brussels next weekend",
        "Volleyball matches near me",
        "Basketball games this month",
        "Women's football in Antwerp"
    ]
    
    print("🧪 Testing LLM Extractor:")
    for query in test_queries:
        try:
            result = extract_filters(query, {"lat": 50.8503, "lon": 4.3517})
            print(f"✅ '{query}' → {result.model_dump_json()}")
        except Exception as e:
            print(f"❌ '{query}' → Error: {e}")

if __name__ == "__main__":
    test_extractor()
