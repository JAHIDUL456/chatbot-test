from fastapi import APIRouter
from app.api.v1.endpoints import insight

# Global router for API version 1
api_router = APIRouter()

# Register endpoint sub-routers under appropriate path prefixes and tags
api_router.include_router(
    insight.router,
    tags=["Shop Insights"]
)

