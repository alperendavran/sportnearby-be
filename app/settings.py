#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Application settings and configuration
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Ollama Configuration
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    
    # Database Configuration
    db_user: str
    db_password: str
    db_name: str
    db_host: str = "localhost"
    db_port: int = 5432
    
    # LangSmith Configuration
    langsmith_tracing: bool = True
    langsmith_endpoint: str = "https://eu.api.smith.langchain.com"
    langsmith_api_key: str
    langsmith_project: str = "geo-agent-sports-events"
    
    # Application Configuration
    project_name: str = "AI Sports Events Agent"
    debug: bool = True

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }


# Global settings instance
settings = Settings()
