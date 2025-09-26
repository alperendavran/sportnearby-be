#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick evaluation runner for Sports Events Agent
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from evaluation.langsmith_evaluator import SportsEventsEvaluator
from evaluation.golden_dataset import GoldenDataset


async def quick_evaluation():
    """Run a quick evaluation with sample test cases"""
    print("🚀 QUICK EVALUATION - SPORTS EVENTS AGENT")
    print("=" * 50)
    
    evaluator = SportsEventsEvaluator()
    dataset = GoldenDataset()
    
    # Check if agent is running
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:8000/health")
            if response.status_code != 200:
                print("❌ Agent is not running. Please start the agent first.")
                print("   Run: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
                return
    except Exception:
        print("❌ Agent is not running. Please start the agent first.")
        print("   Run: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
        return
    
    print("✅ Agent is running. Starting quick evaluation...")
    
    # Test a few sample queries
    sample_queries = [
        "What leagues are available?",
        "Brussels sports events",
        "Matches tomorrow",
        "Pro League matches in Antwerp this weekend",
        "What can I do?"
    ]
    
    print(f"\n🔍 Testing {len(sample_queries)} sample queries:")
    
    results = []
    for i, query in enumerate(sample_queries, 1):
        print(f"\n{i}. Query: '{query}'")
        try:
            response = await evaluator.run_agent_query(query)
            if "error" in response:
                print(f"   ❌ Error: {response['error']}")
            else:
                intent = response.get("intent", "unknown")
                count = response.get("count", 0)
                print(f"   ✅ Intent: {intent}")
                print(f"   📊 Results: {count} events")
                if "filters" in response:
                    filters = response["filters"]
                    if filters.get("cities"):
                        print(f"   📍 Cities: {filters['cities']}")
                    if filters.get("date_from"):
                        print(f"   📅 Date: {filters['date_from']} to {filters['date_to']}")
            results.append({"query": query, "response": response})
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            results.append({"query": query, "error": str(e)})
    
    # Summary
    successful = sum(1 for r in results if "error" not in r and "error" not in r.get("response", {}))
    total = len(results)
    
    print(f"\n📊 QUICK EVALUATION SUMMARY:")
    print(f"   Successful: {successful}/{total}")
    print(f"   Success Rate: {successful/total:.1%}")
    
    if successful == total:
        print("🎉 All test queries passed!")
    else:
        print("⚠️ Some test queries failed. Check the agent logs.")


async def full_evaluation():
    """Run full comprehensive evaluation"""
    print("🚀 FULL EVALUATION - SPORTS EVENTS AGENT")
    print("=" * 50)
    
    evaluator = SportsEventsEvaluator()
    
    # Check if agent is running
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:8000/health")
            if response.status_code != 200:
                print("❌ Agent is not running. Please start the agent first.")
                return
    except Exception:
        print("❌ Agent is not running. Please start the agent first.")
        return
    
    print("✅ Agent is running. Starting full evaluation...")
    
    # Run comprehensive evaluation
    results = await evaluator.run_comprehensive_evaluation()
    
    # Save results
    filename = evaluator.save_results(results)
    
    # Print detailed results
    evaluator.print_detailed_results(results)
    
    print(f"\n🎉 Full evaluation completed!")
    print(f"📁 Results saved to: {filename}")


def show_dataset_info():
    """Show information about the golden dataset"""
    print("📊 GOLDEN DATASET INFORMATION")
    print("=" * 50)
    
    dataset = GoldenDataset()
    stats = dataset.get_statistics()
    
    print(f"Total test cases: {stats['total_test_cases']}")
    
    print(f"\nBy category:")
    for category, count in stats['by_category'].items():
        print(f"  {category}: {count}")
    
    print(f"\nBy difficulty:")
    for difficulty, count in stats['by_difficulty'].items():
        print(f"  {difficulty}: {count}")
    
    print(f"\nBy expected behavior:")
    for behavior, count in stats['by_behavior'].items():
        print(f"  {behavior}: {count}")
    
    # Show sample test cases
    print(f"\nSample test cases:")
    for i, tc in enumerate(dataset.get_all_test_cases()[:5]):
        print(f"\n{i+1}. Query: '{tc.query}'")
        print(f"   Expected Intent: {tc.expected_intent}")
        print(f"   Category: {tc.category}")
        print(f"   Difficulty: {tc.difficulty}")
        print(f"   Expected Behavior: {tc.expected_behavior}")


def main():
    """Main function"""
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "quick":
            asyncio.run(quick_evaluation())
        elif command == "full":
            asyncio.run(full_evaluation())
        elif command == "dataset":
            show_dataset_info()
        else:
            print(f"❌ Unknown command: {command}")
            print("Available commands: quick, full, dataset")
    else:
        print("🏆 SPORTS EVENTS AGENT EVALUATION")
        print("=" * 50)
        print("Available commands:")
        print("  python evaluation/run_evaluation.py quick   - Run quick evaluation")
        print("  python evaluation/run_evaluation.py full    - Run full evaluation")
        print("  python evaluation/run_evaluation.py dataset - Show dataset info")
        print()
        print("Make sure the agent is running first:")
        print("  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")


if __name__ == "__main__":
    main()
