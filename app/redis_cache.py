import redis
import json
import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv(dotenv_path="config.env")

try:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    logger.info(f"Connecting to Redis: {redis_url}")
    r = redis.StrictRedis.from_url(redis_url, decode_responses=True)
    r.ping()
    logger.info("Redis connection established successfully")
except Exception as e:
    logger.error(f"Redis connection failed: {e}")
    r = None

def save_user_query_to_redis(user_id: str, data: dict) -> bool:
    """Save user query data to Redis"""
    logger.info(f"Saving data to Redis for user: {user_id}")
    
    if not r:
        logger.error("Redis not available - skipping save")
        return False
        
    try:
        key = f"user_id:{user_id}:queries"
        r.rpush(key, json.dumps(data))
        r.expire(key, 1 * 24 * 60 * 60)  # 1 day  
        
        logger.info(f"Successfully saved data to Redis for user: {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving to Redis: {e}")
        return False

def get_user_queries_from_redis(user_id: str) -> list:
    """Get all queries for a user"""
    logger.info(f"Retrieving queries from Redis for user: {user_id}")
    
    if not r:
        logger.error("Redis not available")
        return []
        
    try:
        key = f"user_id:{user_id}:queries"
        queries = r.lrange(key, 0, -1)
        
        if not queries:
            logger.info(f"No queries found for user: {user_id}")
            return []
        
        parsed_queries = []
        for query in queries:
            try:
                parsed_queries.append(json.loads(query))
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing query JSON: {e}")
                continue
        
        logger.info(f"Successfully retrieved {len(parsed_queries)} queries for user: {user_id}")
        return parsed_queries
        
    except Exception as e:
        logger.error(f"Error retrieving queries from Redis: {e}")
        return []
