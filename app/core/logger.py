import logging
import sys
from app.core.config import settings


def setup_logging() -> None:
    """
    Configure the application-wide standard logger.
    Sets log level, formatting, and standard output streaming.
    """
    # Determine logging level from settings
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    
    # Clear default root handlers
    logging.root.handlers = []
    
    # Configure base logging
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Fine-tune third-party libraries logging levels to reduce noise in development/production
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("groq").setLevel(logging.INFO)
