#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Golden Dataset for Sports Events Agent Evaluation
Comprehensive test cases covering all user interaction scenarios
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo


@dataclass
class TestCase:
    """Single test case for evaluation"""
    query: str
    expected_intent: str
    expected_slots: Dict[str, Any]
    expected_behavior: str  # "success", "clarification", "error"
    category: str  # "intent_classification", "date_resolution", "location_resolution", "end_to_end"
    difficulty: str  # "easy", "medium", "hard"
    expected_date_range: Optional[Dict[str, Any]] = None
    expected_location: Optional[Dict[str, Any]] = None
    expected_message: Optional[str] = None
    description: str = ""


class GoldenDataset:
    """Golden dataset for comprehensive agent evaluation"""
    
    def __init__(self):
        self.test_cases: List[TestCase] = []
        self._build_dataset()
    
    def _build_dataset(self):
        """Build comprehensive test dataset"""
        
        # =============================================================================
        # INTENT CLASSIFICATION TEST CASES
        # =============================================================================
        
        # List competitions intent
        self.test_cases.extend([
            TestCase(
                query="What leagues are available?",
                expected_intent="list_competitions",
                expected_slots={"competitions": [], "cities": [], "venues": []},
                expected_behavior="success",
                category="intent_classification",
                difficulty="easy",
                description="Basic competition listing query"
            ),
            TestCase(
                query="Hangi ligler var?",
                expected_intent="list_competitions",
                expected_slots={"competitions": [], "cities": [], "venues": []},
                expected_behavior="success",
                category="intent_classification",
                difficulty="easy",
                description="Turkish competition listing query"
            ),
            TestCase(
                query="Show me all competitions",
                expected_intent="list_competitions",
                expected_slots={"competitions": [], "cities": [], "venues": []},
                expected_behavior="success",
                category="intent_classification",
                difficulty="easy",
                description="Alternative competition listing query"
            ),
        ])
        
        # Events near location intent
        self.test_cases.extend([
            TestCase(
                query="Brussels sports events",
                expected_intent="events_in_cities",
                expected_slots={"cities": ["Brussels"], "competitions": [], "venues": []},
                expected_behavior="success",
                category="intent_classification",
                difficulty="easy",
                description="City-specific events query"
            ),
            TestCase(
                query="Matches in Antwerp",
                expected_intent="events_in_cities",
                expected_slots={"cities": ["Antwerp"], "competitions": [], "venues": []},
                expected_behavior="success",
                category="intent_classification",
                difficulty="easy",
                description="Alternative city events query"
            ),
            TestCase(
                query="Events near me",
                expected_intent="events_near",
                expected_slots={"cities": [], "competitions": [], "venues": []},
                expected_behavior="success",
                category="intent_classification",
                difficulty="medium",
                description="Location-based events query"
            ),
        ])
        
        # Competition-specific events
        self.test_cases.extend([
            TestCase(
                query="Pro League matches",
                expected_intent="events_by_competition",
                expected_slots={"competitions": ["Pro League"], "cities": [], "venues": []},
                expected_behavior="success",
                category="intent_classification",
                difficulty="easy",
                description="Competition-specific events query"
            ),
            TestCase(
                query="Jupiler League games",
                expected_intent="events_by_competition",
                expected_slots={"competitions": ["Jupiler League"], "cities": [], "venues": []},
                expected_behavior="success",
                category="intent_classification",
                difficulty="easy",
                description="Alternative competition query"
            ),
        ])
        
        # Venue-specific events
        self.test_cases.extend([
            TestCase(
                query="Lotto Park matches",
                expected_intent="events_by_venue",
                expected_slots={"venues": ["Lotto Park"], "cities": [], "competitions": []},
                expected_behavior="success",
                category="intent_classification",
                difficulty="medium",
                description="Venue-specific events query"
            ),
            TestCase(
                query="Next event at King Baudouin Stadium",
                expected_intent="next_at_venue",
                expected_slots={"venues": ["King Baudouin Stadium"], "cities": [], "competitions": []},
                expected_behavior="success",
                category="intent_classification",
                difficulty="medium",
                description="Next event at venue query"
            ),
        ])
        
        # General inquiry
        self.test_cases.extend([
            TestCase(
                query="What can I do?",
                expected_intent="general_inquiry",
                expected_slots={"cities": [], "competitions": [], "venues": []},
                expected_behavior="success",
                expected_message="Please ask a more specific question about sports events.",
                category="intent_classification",
                difficulty="easy",
                description="General inquiry query"
            ),
            TestCase(
                query="Sports activities",
                expected_intent="general_inquiry",
                expected_slots={"cities": [], "competitions": [], "venues": []},
                expected_behavior="success",
                expected_message="Please ask a more specific question about sports events.",
                category="intent_classification",
                difficulty="easy",
                description="Vague sports query"
            ),
        ])
        
        # =============================================================================
        # DATE RESOLUTION TEST CASES
        # =============================================================================
        
        # Clear date expressions
        self.test_cases.extend([
            TestCase(
                query="Brussels events this weekend",
                expected_intent="events_in_cities",
                expected_slots={"cities": ["Brussels"], "competitions": [], "venues": []},
                expected_date_range={"status": "OK", "time_keyword": "this_weekend"},
                expected_behavior="success",
                category="date_resolution",
                difficulty="easy",
                description="Clear weekend date expression"
            ),
            TestCase(
                query="Matches tomorrow",
                expected_intent="events_near",
                expected_slots={"cities": [], "competitions": [], "venues": []},
                expected_date_range={"status": "OK", "time_keyword": "tomorrow"},
                expected_behavior="success",
                category="date_resolution",
                difficulty="easy",
                description="Clear tomorrow date expression"
            ),
            TestCase(
                query="Antwerp events next week",
                expected_intent="events_in_cities",
                expected_slots={"cities": ["Antwerp"], "competitions": [], "venues": []},
                expected_date_range={"status": "OK", "time_keyword": "next_week"},
                expected_behavior="success",
                category="date_resolution",
                difficulty="easy",
                description="Clear next week date expression"
            ),
            TestCase(
                query="Brussels events next year",
                expected_intent="events_in_cities",
                expected_slots={"cities": ["Brussels"], "competitions": [], "venues": []},
                expected_date_range={"status": "OK", "time_keyword": "next_year"},
                expected_behavior="success",
                category="date_resolution",
                difficulty="medium",
                description="Next year date expression"
            ),
            TestCase(
                query="Events within 8 weeks",
                expected_intent="events_near",
                expected_slots={"cities": [], "competitions": [], "venues": []},
                expected_date_range={"status": "OK", "time_keyword": "weeks_ahead"},
                expected_behavior="success",
                category="date_resolution",
                difficulty="medium",
                description="Weeks ahead date expression"
            ),
        ])
        
        # No time expressions
        self.test_cases.extend([
            TestCase(
                query="Brussels sports events",
                expected_intent="events_in_cities",
                expected_slots={"cities": ["Brussels"], "competitions": [], "venues": []},
                expected_date_range={"status": "NO_TIME"},
                expected_behavior="success",
                category="date_resolution",
                difficulty="easy",
                description="No time expression - should default to today"
            ),
            TestCase(
                query="Pro League matches",
                expected_intent="events_by_competition",
                expected_slots={"competitions": ["Pro League"], "cities": [], "venues": []},
                expected_date_range={"status": "NO_TIME"},
                expected_behavior="success",
                category="date_resolution",
                difficulty="easy",
                description="No time expression for competition query"
            ),
        ])
        
        # Unclear date expressions
        self.test_cases.extend([
            TestCase(
                query="Brussels events soon",
                expected_intent="events_in_cities",
                expected_slots={"cities": ["Brussels"], "competitions": [], "venues": []},
                expected_date_range={"status": "UNCLEAR"},
                expected_behavior="success",
                expected_message="Tarih ifadesi belirsiz olduğu için önümüzdeki 10 günlük etkinlikler gösteriliyor.",
                category="date_resolution",
                difficulty="hard",
                description="Unclear date expression - should use 10-day fallback"
            ),
            TestCase(
                query="Matches later",
                expected_intent="events_near",
                expected_slots={"cities": [], "competitions": [], "venues": []},
                expected_date_range={"status": "UNCLEAR"},
                expected_behavior="success",
                expected_message="Tarih ifadesi belirsiz olduğu için önümüzdeki 10 günlük etkinlikler gösteriliyor.",
                category="date_resolution",
                difficulty="hard",
                description="Unclear date expression - should use 10-day fallback"
            ),
        ])
        
        # =============================================================================
        # LOCATION RESOLUTION TEST CASES
        # =============================================================================
        
        # Clear city names
        self.test_cases.extend([
            TestCase(
                query="Brussels sports events",
                expected_intent="events_in_cities",
                expected_slots={"cities": ["Brussels"], "competitions": [], "venues": []},
                expected_location={"status": "OK", "cities": ["Brussels"]},
                expected_behavior="success",
                category="location_resolution",
                difficulty="easy",
                description="Clear Brussels city name"
            ),
            TestCase(
                query="Antwerp matches",
                expected_intent="events_in_cities",
                expected_slots={"cities": ["Antwerp"], "competitions": [], "venues": []},
                expected_location={"status": "OK", "cities": ["Antwerp"]},
                expected_behavior="success",
                category="location_resolution",
                difficulty="easy",
                description="Clear Antwerp city name"
            ),
            TestCase(
                query="Ghent sports events",
                expected_intent="events_in_cities",
                expected_slots={"cities": ["Ghent"], "competitions": [], "venues": []},
                expected_location={"status": "OK", "cities": ["Ghent"]},
                expected_behavior="success",
                category="location_resolution",
                difficulty="easy",
                description="Clear Ghent city name"
            ),
        ])
        
        # Multiple cities
        self.test_cases.extend([
            TestCase(
                query="Brussels and Antwerp events",
                expected_intent="events_in_cities",
                expected_slots={"cities": ["Brussels", "Antwerp"], "competitions": [], "venues": []},
                expected_location={"status": "OK", "cities": ["Brussels", "Antwerp"]},
                expected_behavior="success",
                category="location_resolution",
                difficulty="medium",
                description="Multiple cities in query"
            ),
            TestCase(
                query="Events in Brussels, Antwerp, Ghent",
                expected_intent="events_in_cities",
                expected_slots={"cities": ["Brussels", "Antwerp", "Ghent"], "competitions": [], "venues": []},
                expected_location={"status": "OK", "cities": ["Brussels", "Antwerp", "Ghent"]},
                expected_behavior="success",
                category="location_resolution",
                difficulty="medium",
                description="Comma-separated cities"
            ),
        ])
        
        # No location specified
        self.test_cases.extend([
            TestCase(
                query="Sports events",
                expected_intent="general_inquiry",
                expected_slots={"cities": [], "competitions": [], "venues": []},
                expected_location={"status": "NO_LOCATION"},
                expected_behavior="success",
                expected_message="Please ask a more specific question about sports events.",
                category="location_resolution",
                difficulty="medium",
                description="No location specified - should use Brussels fallback"
            ),
            TestCase(
                query="What matches are available?",
                expected_intent="general_inquiry",
                expected_slots={"cities": [], "competitions": [], "venues": []},
                expected_location={"status": "NO_LOCATION"},
                expected_behavior="success",
                expected_message="Please ask a more specific question about sports events.",
                category="location_resolution",
                difficulty="medium",
                description="General inquiry - should use Brussels fallback"
            ),
            TestCase(
                query="What matches are available?",
                expected_intent="general_inquiry",
                expected_slots={"cities": [], "competitions": [], "venues": []},
                expected_location={"status": "NO_LOCATION"},
                expected_behavior="clarification",
                expected_message="Location not specified. Please add a city name or share your coordinates.",
                category="location_resolution",
                difficulty="medium",
                description="Vague location query"
            ),
        ])
        
        # =============================================================================
        # END-TO-END TEST CASES
        # =============================================================================
        
        # Complex queries
        self.test_cases.extend([
            TestCase(
                query="Pro League matches in Brussels this weekend",
                expected_intent="events_in_cities",
                expected_slots={"competitions": [], "cities": ["Brussels"], "venues": []},
                expected_date_range={"status": "OK", "time_keyword": "this_weekend"},
                expected_location={"status": "OK", "cities": ["Brussels"]},
                expected_behavior="success",
                category="end_to_end",
                difficulty="medium",
                description="Complex query with competition, location, and time - currently classified as events_in_cities"
            ),
            TestCase(
                query="Next event at Lotto Park tomorrow",
                expected_intent="next_at_venue",
                expected_slots={"venues": ["Lotto Park"], "cities": [], "competitions": []},
                expected_date_range={"status": "OK", "time_keyword": "tomorrow"},
                expected_location={"status": "OK", "venues": ["Lotto Park"]},
                expected_behavior="success",
                category="end_to_end",
                difficulty="medium",
                description="Venue-specific query with time"
            ),
            TestCase(
                query="Jupiler League matches in Antwerp and Ghent next week",
                expected_intent="events_in_cities",
                expected_slots={"competitions": [], "cities": ["Antwerp", "Ghent"], "venues": []},
                expected_date_range={"status": "OK", "time_keyword": "next_week"},
                expected_location={"status": "OK", "cities": ["Antwerp", "Ghent"]},
                expected_behavior="success",
                category="end_to_end",
                difficulty="hard",
                description="Complex multi-city, competition, and time query - currently classified as events_in_cities"
            ),
        ])
        
        # Edge cases
        self.test_cases.extend([
            TestCase(
                query="",
                expected_intent="general_inquiry",
                expected_slots={"cities": [], "competitions": [], "venues": []},
                expected_behavior="error",
                category="end_to_end",
                difficulty="hard",
                description="Empty query"
            ),
            TestCase(
                query="xyz123 random text",
                expected_intent="general_inquiry",
                expected_slots={"cities": [], "competitions": [], "venues": []},
                expected_behavior="error",
                category="end_to_end",
                difficulty="hard",
                description="Nonsensical query"
            ),
            TestCase(
                query="Events in Paris next weekend",
                expected_intent="events_in_cities",
                expected_slots={"cities": ["Paris"], "competitions": [], "venues": []},
                expected_date_range={"status": "OK", "time_keyword": "next_weekend"},
                expected_location={"status": "OK", "cities": ["Paris"]},
                expected_behavior="success",
                category="end_to_end",
                difficulty="medium",
                description="Non-Belgium city (should work but return low confidence)"
            ),
        ])
        
        # Turkish queries
        self.test_cases.extend([
            TestCase(
                query="Brüksel spor etkinlikleri",
                expected_intent="events_in_cities",
                expected_slots={"cities": ["Brussels"], "competitions": [], "venues": []},
                expected_location={"status": "OK", "cities": ["Brussels"]},
                expected_behavior="success",
                category="end_to_end",
                difficulty="medium",
                description="Turkish city name"
            ),
            TestCase(
                query="Bu hafta sonu Antwerp maçları",
                expected_intent="events_in_cities",
                expected_slots={"cities": ["Antwerp"], "competitions": [], "venues": []},
                expected_date_range={"status": "OK", "time_keyword": "this_weekend"},
                expected_location={"status": "OK", "cities": ["Antwerp"]},
                expected_behavior="success",
                category="end_to_end",
                difficulty="medium",
                description="Turkish time and location expression"
            ),
            TestCase(
                query="Yakınımdaki spor etkinlikleri",
                expected_intent="events_near",
                expected_slots={"cities": [], "competitions": [], "venues": []},
                expected_behavior="success",
                category="end_to_end",
                difficulty="medium",
                description="Turkish 'near me' expression"
            ),
        ])
    
    def get_test_cases_by_category(self, category: str) -> List[TestCase]:
        """Get test cases by category"""
        return [tc for tc in self.test_cases if tc.category == category]
    
    def get_test_cases_by_difficulty(self, difficulty: str) -> List[TestCase]:
        """Get test cases by difficulty"""
        return [tc for tc in self.test_cases if tc.difficulty == difficulty]
    
    def get_all_test_cases(self) -> List[TestCase]:
        """Get all test cases"""
        return self.test_cases
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get dataset statistics"""
        total = len(self.test_cases)
        by_category = {}
        by_difficulty = {}
        by_behavior = {}
        
        for tc in self.test_cases:
            # Category stats
            by_category[tc.category] = by_category.get(tc.category, 0) + 1
            
            # Difficulty stats
            by_difficulty[tc.difficulty] = by_difficulty.get(tc.difficulty, 0) + 1
            
            # Behavior stats
            by_behavior[tc.expected_behavior] = by_behavior.get(tc.expected_behavior, 0) + 1
        
        return {
            "total_test_cases": total,
            "by_category": by_category,
            "by_difficulty": by_difficulty,
            "by_behavior": by_behavior
        }
    
    def export_to_json(self, filename: str = "golden_dataset.json"):
        """Export test cases to JSON file"""
        import json
        
        data = {
            "metadata": {
                "description": "Golden Dataset for Sports Events Agent Evaluation",
                "created_at": datetime.now().isoformat(),
                "total_cases": len(self.test_cases)
            },
            "statistics": self.get_statistics(),
            "test_cases": [
                {
                    "query": tc.query,
                    "expected_intent": tc.expected_intent,
                    "expected_slots": tc.expected_slots,
                    "expected_date_range": tc.expected_date_range,
                    "expected_location": tc.expected_location,
                    "expected_behavior": tc.expected_behavior,
                    "expected_message": tc.expected_message,
                    "category": tc.category,
                    "difficulty": tc.difficulty,
                    "description": tc.description
                }
                for tc in self.test_cases
            ]
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Golden dataset exported to {filename}")
        return filename


def main():
    """Main function to demonstrate the golden dataset"""
    dataset = GoldenDataset()
    
    print("=" * 80)
    print("🏆 GOLDEN DATASET FOR SPORTS EVENTS AGENT EVALUATION")
    print("=" * 80)
    
    # Show statistics
    stats = dataset.get_statistics()
    print(f"\n📊 DATASET STATISTICS:")
    print(f"Total test cases: {stats['total_test_cases']}")
    
    print(f"\n📋 BY CATEGORY:")
    for category, count in stats['by_category'].items():
        print(f"  {category}: {count}")
    
    print(f"\n🎯 BY DIFFICULTY:")
    for difficulty, count in stats['by_difficulty'].items():
        print(f"  {difficulty}: {count}")
    
    print(f"\n🎭 BY EXPECTED BEHAVIOR:")
    for behavior, count in stats['by_behavior'].items():
        print(f"  {behavior}: {count}")
    
    # Show sample test cases
    print(f"\n🔍 SAMPLE TEST CASES:")
    for i, tc in enumerate(dataset.get_all_test_cases()[:5]):
        print(f"\n{i+1}. Query: '{tc.query}'")
        print(f"   Expected Intent: {tc.expected_intent}")
        print(f"   Category: {tc.category}")
        print(f"   Difficulty: {tc.difficulty}")
        print(f"   Expected Behavior: {tc.expected_behavior}")
        print(f"   Description: {tc.description}")
    
    # Export to JSON
    print(f"\n💾 EXPORTING DATASET...")
    filename = dataset.export_to_json()
    
    print(f"\n✅ Golden dataset created successfully!")
    print(f"📁 File: {filename}")
    print(f"📊 Total test cases: {len(dataset.get_all_test_cases())}")


if __name__ == "__main__":
    main()
