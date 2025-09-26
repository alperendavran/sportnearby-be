#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI application entry point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .settings import settings
from .db import create_pool, close_pool
from .api import register_routes


# Create FastAPI app
app = FastAPI(
    title=settings.project_name,
    version="0.3.0",
    description="AI Sports Events Agent - Natural language sports event search"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
    allow_methods=["*"],
)

# Register API routes
register_routes(app)


@app.on_event("startup")
async def startup_event():
    """Initialize database connection pool"""
    await create_pool()
    print(f"✅ {settings.project_name} started successfully")
    print(f"🔗 Database: {settings.db_host}:{settings.db_port}/{settings.db_name}")
    print(f"🤖 Ollama: {settings.ollama_host}/{settings.ollama_model}")
    if settings.langsmith_tracing:
        print(f"📊 LangSmith: {settings.langsmith_project}")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources"""
    await close_pool()
    print("✅ Application shutdown complete")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
