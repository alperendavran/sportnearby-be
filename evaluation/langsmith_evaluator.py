#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangSmith Evaluation System for Sports Events Agent
Automated evaluation using golden dataset
"""

import asyncio
import json
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

import httpx
from langsmith import Client
from langsmith.evaluation import evaluate, LangChainStringEvaluator
from langsmith.schemas import Run, Example

from .golden_dataset import GoldenDataset, TestCase
from app.settings import settings


class SportsEventsEvaluator:
    """LangSmith-based evaluator for Sports Events Agent"""
    
    def __init__(self):
        self.client = Client(
            api_key=settings.langsmith_api_key,
            api_url=settings.langsmith_endpoint
        )
        self.dataset = GoldenDataset()
        self.base_url = "http://localhost:8000"
        
    async def run_agent_query(self, query: str, lat: Optional[float] = None, 
                            lon: Optional[float] = None, limit: int = 20) -> Dict[str, Any]:
        """Run a query against the agent"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {"q": query, "limit": limit}
                if lat is not None:
                    params["lat"] = lat
                if lon is not None:
                    params["lon"] = lon
                
                response = await client.get(f"{self.base_url}/agent/query", params=params)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            return {
                "error": str(e),
                "status": "error"
            }
    
    def create_langsmith_dataset(self, dataset_name: str = "sports-events-golden") -> str:
        """Create LangSmith dataset from golden dataset"""
        try:
            # Create dataset
            dataset = self.client.create_dataset(
                dataset_name=dataset_name,
                description="Golden dataset for Sports Events Agent evaluation"
            )
            
            # Add examples to dataset
            examples = []
            for i, test_case in enumerate(self.dataset.get_all_test_cases()):
                example = self.client.create_example(
                    inputs={"query": test_case.query},
                    outputs={
                        "expected_intent": test_case.expected_intent,
                        "expected_slots": test_case.expected_slots,
                        "expected_behavior": test_case.expected_behavior,
                        "expected_message": test_case.expected_message,
                        "category": test_case.category,
                        "difficulty": test_case.difficulty
                    },
                    dataset_id=dataset.id
                )
                examples.append(example)
            
            print(f"✅ Created LangSmith dataset: {dataset_name}")
            print(f"📊 Added {len(examples)} examples")
            return dataset.id
            
        except Exception as e:
            print(f"❌ Error creating dataset: {e}")
            return None
    
    async def evaluate_intent_classification(self, test_cases: List[TestCase]) -> Dict[str, Any]:
        """Evaluate intent classification accuracy"""
        results = {
            "total": len(test_cases),
            "correct": 0,
            "incorrect": 0,
            "errors": 0,
            "accuracy": 0.0,
            "details": []
        }
        
        for test_case in test_cases:
            try:
                response = await self.run_agent_query(test_case.query)
                
                if "error" in response:
                    results["errors"] += 1
                    results["details"].append({
                        "query": test_case.query,
                        "expected": test_case.expected_intent,
                        "actual": "ERROR",
                        "correct": False,
                        "error": response["error"]
                    })
                else:
                    actual_intent = response.get("intent", "unknown")
                    is_correct = actual_intent == test_case.expected_intent
                    
                    if is_correct:
                        results["correct"] += 1
                    else:
                        results["incorrect"] += 1
                    
                    results["details"].append({
                        "query": test_case.query,
                        "expected": test_case.expected_intent,
                        "actual": actual_intent,
                        "correct": is_correct,
                        "response": response
                    })
                
                # Small delay to avoid overwhelming the server
                await asyncio.sleep(0.1)
                
            except Exception as e:
                results["errors"] += 1
                results["details"].append({
                    "query": test_case.query,
                    "expected": test_case.expected_intent,
                    "actual": "EXCEPTION",
                    "correct": False,
                    "error": str(e)
                })
        
        results["accuracy"] = results["correct"] / results["total"] if results["total"] > 0 else 0.0
        return results
    
    async def evaluate_date_resolution(self, test_cases: List[TestCase]) -> Dict[str, Any]:
        """Evaluate date resolution accuracy"""
        results = {
            "total": len(test_cases),
            "correct": 0,
            "incorrect": 0,
            "errors": 0,
            "accuracy": 0.0,
            "details": []
        }
        
        for test_case in test_cases:
            try:
                response = await self.run_agent_query(test_case.query)
                
                if "error" in response:
                    results["errors"] += 1
                    results["details"].append({
                        "query": test_case.query,
                        "expected": test_case.expected_date_range,
                        "actual": "ERROR",
                        "correct": False,
                        "error": response["error"]
                    })
                else:
                    # Check if date resolution matches expected behavior
                    filters = response.get("filters", {})
                    actual_date_from = filters.get("date_from")
                    actual_date_to = filters.get("date_to")
                    actual_time_keyword = filters.get("time_keyword")
                    
                    expected_status = test_case.expected_date_range.get("status") if test_case.expected_date_range else "NO_TIME"
                    expected_time_keyword = test_case.expected_date_range.get("time_keyword") if test_case.expected_date_range else None
                    
                    # Improved validation logic
                    is_correct = False
                    
                    if expected_status == "OK":
                        # For OK status, check if dates are resolved and time_keyword matches
                        if actual_date_from and (actual_date_to or expected_time_keyword == "tomorrow"):
                            if expected_time_keyword is None or actual_time_keyword == expected_time_keyword:
                                is_correct = True
                    elif expected_status == "NO_TIME":
                        # For NO_TIME, check if it defaults to today (current behavior)
                        if actual_date_from and actual_date_to and actual_date_from == actual_date_to:
                            is_correct = True
                    elif expected_status == "UNCLEAR":
                        # For UNCLEAR, check if fallback mechanism is used (10-day range)
                        if actual_date_from and actual_date_to:
                            from datetime import datetime, timedelta
                            try:
                                date_from = datetime.fromisoformat(actual_date_from).date()
                                date_to = datetime.fromisoformat(actual_date_to).date()
                                # Check if it's approximately 10 days (fallback mechanism)
                                if 8 <= (date_to - date_from).days <= 12:
                                    is_correct = True
                            except:
                                pass
                    
                    if is_correct:
                        results["correct"] += 1
                    else:
                        results["incorrect"] += 1
                    
                    results["details"].append({
                        "query": test_case.query,
                        "expected": test_case.expected_date_range,
                        "actual": {
                            "date_from": actual_date_from, 
                            "date_to": actual_date_to,
                            "time_keyword": actual_time_keyword
                        },
                        "correct": is_correct,
                        "response": response
                    })
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                results["errors"] += 1
                results["details"].append({
                    "query": test_case.query,
                    "expected": test_case.expected_date_range,
                    "actual": "EXCEPTION",
                    "correct": False,
                    "error": str(e)
                })
        
        results["accuracy"] = results["correct"] / results["total"] if results["total"] > 0 else 0.0
        return results
    
    async def evaluate_location_resolution(self, test_cases: List[TestCase]) -> Dict[str, Any]:
        """Evaluate location resolution accuracy"""
        results = {
            "total": len(test_cases),
            "correct": 0,
            "incorrect": 0,
            "errors": 0,
            "accuracy": 0.0,
            "details": []
        }
        
        for test_case in test_cases:
            try:
                response = await self.run_agent_query(test_case.query)
                
                if "error" in response:
                    results["errors"] += 1
                    results["details"].append({
                        "query": test_case.query,
                        "expected": test_case.expected_location,
                        "actual": "ERROR",
                        "correct": False,
                        "error": response["error"]
                    })
                else:
                    # Check if location resolution matches expected behavior
                    filters = response.get("filters", {})
                    actual_cities = filters.get("cities", [])
                    
                    expected_cities = test_case.expected_location.get("cities", []) if test_case.expected_location else []
                    
                    # Simple validation logic
                    is_correct = False
                    if set(actual_cities) == set(expected_cities):
                        is_correct = True
                    elif test_case.expected_behavior == "clarification" and "error" in response:
                        is_correct = True
                    
                    if is_correct:
                        results["correct"] += 1
                    else:
                        results["incorrect"] += 1
                    
                    results["details"].append({
                        "query": test_case.query,
                        "expected": test_case.expected_location,
                        "actual": {"cities": actual_cities},
                        "correct": is_correct,
                        "response": response
                    })
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                results["errors"] += 1
                results["details"].append({
                    "query": test_case.query,
                    "expected": test_case.expected_location,
                    "actual": "EXCEPTION",
                    "correct": False,
                    "error": str(e)
                })
        
        results["accuracy"] = results["correct"] / results["total"] if results["total"] > 0 else 0.0
        return results
    
    async def run_comprehensive_evaluation(self) -> Dict[str, Any]:
        """Run comprehensive evaluation across all categories"""
        print("🚀 Starting comprehensive evaluation...")
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "total_test_cases": len(self.dataset.get_all_test_cases()),
            "categories": {}
        }
        
        # Evaluate each category
        categories = ["intent_classification", "date_resolution", "location_resolution", "end_to_end"]
        
        for category in categories:
            print(f"\n📊 Evaluating {category}...")
            test_cases = self.dataset.get_test_cases_by_category(category)
            
            if category == "intent_classification":
                category_results = await self.evaluate_intent_classification(test_cases)
            elif category == "date_resolution":
                category_results = await self.evaluate_date_resolution(test_cases)
            elif category == "location_resolution":
                category_results = await self.evaluate_location_resolution(test_cases)
            else:  # end_to_end
                # For end-to-end, we'll use intent classification as a proxy
                category_results = await self.evaluate_intent_classification(test_cases)
            
            results["categories"][category] = category_results
            
            print(f"✅ {category}: {category_results['accuracy']:.2%} accuracy")
            print(f"   Correct: {category_results['correct']}")
            print(f"   Incorrect: {category_results['incorrect']}")
            print(f"   Errors: {category_results['errors']}")
        
        # Calculate overall accuracy
        total_correct = sum(cat["correct"] for cat in results["categories"].values())
        total_tests = sum(cat["total"] for cat in results["categories"].values())
        results["overall_accuracy"] = total_correct / total_tests if total_tests > 0 else 0.0
        
        print(f"\n🎯 OVERALL ACCURACY: {results['overall_accuracy']:.2%}")
        
        return results
    
    def save_results(self, results: Dict[str, Any], filename: str = None) -> str:
        """Save evaluation results to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"evaluation_results_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Results saved to: {filename}")
        return filename
    
    def print_detailed_results(self, results: Dict[str, Any]):
        """Print detailed evaluation results"""
        print("\n" + "=" * 80)
        print("📊 DETAILED EVALUATION RESULTS")
        print("=" * 80)
        
        print(f"🕐 Timestamp: {results['timestamp']}")
        print(f"📈 Overall Accuracy: {results['overall_accuracy']:.2%}")
        print(f"📊 Total Test Cases: {results['total_test_cases']}")
        
        for category, category_results in results["categories"].items():
            print(f"\n📋 {category.upper()}:")
            print(f"   Accuracy: {category_results['accuracy']:.2%}")
            print(f"   Correct: {category_results['correct']}")
            print(f"   Incorrect: {category_results['incorrect']}")
            print(f"   Errors: {category_results['errors']}")
            
            # Show some incorrect examples
            incorrect_examples = [d for d in category_results['details'] if not d['correct']]
            if incorrect_examples:
                print(f"   ❌ Incorrect Examples:")
                for example in incorrect_examples[:3]:  # Show first 3
                    print(f"      Query: '{example['query']}'")
                    print(f"      Expected: {example['expected']}")
                    print(f"      Actual: {example['actual']}")
                    print()


async def main():
    """Main evaluation function"""
    print("🏆 SPORTS EVENTS AGENT EVALUATION")
    print("=" * 50)
    
    evaluator = SportsEventsEvaluator()
    
    # Check if agent is running
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:8000/health")
            if response.status_code != 200:
                print("❌ Agent is not running. Please start the agent first.")
                return
    except Exception:
        print("❌ Agent is not running. Please start the agent first.")
        return
    
    print("✅ Agent is running. Starting evaluation...")
    
    # Run comprehensive evaluation
    results = await evaluator.run_comprehensive_evaluation()
    
    # Save results
    filename = evaluator.save_results(results)
    
    # Print detailed results
    evaluator.print_detailed_results(results)
    
    print(f"\n🎉 Evaluation completed!")
    print(f"📁 Results saved to: {filename}")


if __name__ == "__main__":
    asyncio.run(main())
