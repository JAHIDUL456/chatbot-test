from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables and .env file.
    Utilizes Pydantic Settings v2 for robust validation and type coercion.
    """
    # FastAPI Application Settings
    PROJECT_NAME: str = "FastAPI Groq Base"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    
    # Groq API Configuration
    GROQ_API_KEY: str
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    
    # CORS Configuration
    BACKEND_CORS_ORIGINS: List[str] = ["*"]

    # Configure Pydantic Settings behavior
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # Ignore additional env variables not defined here
    )


# Instantiate settings singleton to be imported throughout the project
settings = Settings()
