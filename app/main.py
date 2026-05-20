import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logger import setup_logging
from app.api.v1.api import api_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Asynchronous context manager to manage application startup and shutdown events.
    """
    # 1. Initialize logging format and level
    setup_logging()
    logger.info("Initializing FastAPI Application base...")
    
    # 2. Run sanity check on critical external environment variables
    if not settings.GROQ_API_KEY:
        logger.warning(
            "CRITICAL WARNING: GROQ_API_KEY environment variable is not defined. "
            "Calls to /api/v1/chat/ will fail."
        )
    else:
        logger.info("Groq API client credentials validated.")

    yield
    
    # 3. Handle shutdown and connection release if any
    logger.info("Application is shutting down. Cleaning up connections...")


# Initialize the main FastAPI application instance
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Production-grade FastAPI base integrated with Groq LLM API",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Configure Cross-Origin Resource Sharing (CORS) Middleware
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include the main router holding all modular sub-routes
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["App Health Status"])
async def health_check() -> dict:
    """
    Base health-check endpoint. Returns server operational status and docs link.
    """
    return {
        "status": "operational",
        "project": settings.PROJECT_NAME,
        "documentation": "/docs",
        "api_prefix": settings.API_V1_STR
    }
