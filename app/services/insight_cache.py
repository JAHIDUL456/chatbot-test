import time
import hashlib
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class InsightCache:
    """
    In-memory TTL Cache with FIFO eviction to minimize Groq LLM API requests.
    Prevents repeated calls for the same shop parameters and calculated metrics.
    """
    def __init__(self, ttl_seconds: int = 3600, max_size: int = 2000) -> None:
        self.ttl = ttl_seconds
        self.max_size = max_size
        self.cache: Dict[str, Dict[str, Any]] = {}

    def _hash_payload(self, shop_name: str, period: str, summary_dict: Dict[str, Any]) -> str:
        # Create a unique SHA256 signature for the shop's key parameters and metrics
        serialized = json.dumps({
            "shop_name": shop_name.strip().lower(),
            "period": period.strip().lower(),
            "summary": summary_dict
        }, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, shop_name: str, period: str, summary_dict: Dict[str, Any]) -> Optional[str]:
        cache_key = self._hash_payload(shop_name, period, summary_dict)
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            # Check if entry is still fresh
            if time.time() - entry["timestamp"] < self.ttl:
                logger.info(f"Cache hit for shop '{shop_name}' with key: {cache_key[:8]}")
                return entry["value"]
            else:
                # Evict expired entry
                logger.debug(f"Cache expired for shop '{shop_name}' with key: {cache_key[:8]}")
                del self.cache[cache_key]
        return None

    def set(self, shop_name: str, period: str, summary_dict: Dict[str, Any], value: str) -> None:
        cache_key = self._hash_payload(shop_name, period, summary_dict)
        
        # Evict oldest entry if size limit is exceeded (FIFO)
        if len(self.cache) >= self.max_size:
            oldest_key = next(iter(self.cache))
            logger.debug(f"Cache size limit reached. Evicting oldest key: {oldest_key[:8]}")
            del self.cache[oldest_key]
            
        self.cache[cache_key] = {
            "value": value,
            "timestamp": time.time()
        }
        logger.debug(f"Cached new entry for shop '{shop_name}' with key: {cache_key[:8]}")


# Global singleton cache instance with 1 hour TTL
insight_cache = InsightCache(ttl_seconds=3600, max_size=2000)
