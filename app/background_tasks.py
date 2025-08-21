import logging
from app.redis_cache import warm_cache_for_user

logger = logging.getLogger(__name__)

def warm_cache_for_user_background(user_id: str, store_id: str):
    """Simple background cache warming"""
    try:
        warm_cache_for_user(user_id, store_id)
        logger.info(f"Background cache warming completed for user: {user_id}")
    except Exception as e:
        logger.error(f"Error in background cache warming: {e}")

logger.info("Background tasks module loaded")
