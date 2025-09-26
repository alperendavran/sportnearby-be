#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangSmith tracing test
"""

import os
import asyncio
from langsmith import Client
from langsmith import traceable
# from langchain.callbacks.tracers import wait_for_all_tracers


@traceable(project_name="geo-agent-sports-events")
async def test_function():
    """Test function for LangSmith tracing"""
    print("🔍 Test function çalışıyor...")
    result = "Hello from LangSmith!"
    print(f"✅ Result: {result}")
    return result

@traceable(project_name="geo-agent-sports-events")
async def geocode_test():
    """Geocoding test with LangSmith"""
    print("🌍 Geocoding test...")
    
    # Simulate geocoding
    result = {
        "lat": 50.85,
        "lon": 4.35,
        "confidence": 100,
        "status": "OK",
        "source_text": "Brussels",
        "provider": "ollama"
    }
    
    print(f"✅ Geocode result: {result}")
    return result

async def main():
    print("🚀 LangSmith Test Başlatılıyor...")
    
    # Test 1: Simple function
    result1 = await test_function()
    
    # Test 2: Geocoding function
    result2 = await geocode_test()
    
    print("✅ LangSmith Test Tamamlandı!")
    print(f"🔗 LangSmith URL: https://smith.langchain.com/projects/geo-agent-sports-events")
    
    # Tüm trace'lerin gönderilmesini bekle
    print("⏳ Trace'ler gönderiliyor...")
    await asyncio.sleep(2)  # Trace'lerin gönderilmesi için bekle
    print("✅ Tüm trace'ler gönderildi!")

if __name__ == "__main__":
    asyncio.run(main())
