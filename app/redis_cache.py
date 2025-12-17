# import redis
# import json
# import os
# import logging
# from dotenv import load_dotenv
# from datetime import datetime
# from typing import Dict, Any, Optional
# import hashlib

# logger = logging.getLogger(__name__)
# load_dotenv(override=True)

# CACHE_TTL_SECONDS = 172800
# FREQUENT_CACHE_TTL = 259200
# SIMILARITY_CACHE_TTL = 86400

# try:
#     redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
#     logger.info(f"Connecting to Redis with caching: {redis_url}")
#     r = redis.StrictRedis.from_url(redis_url, decode_responses=True)
#     r.ping()
#     logger.info("Redis connection established successfully")
# except Exception as e:
#     logger.error(f"Redis connection failed: {e}")
#     r = None

# def save_user_query_to_redis(user_id: str, data: dict) -> bool:
#     """Save user query data to Redis"""
#     logger.info(f"Saving data to Redis for user: {user_id}")
#     if not r:
#         logger.error("Redis not available - skipping save")
#         return False
#     try:
#         # Main user queries with 2-day TTL
#         key = f"user_id:{user_id}:queries"
#         r.rpush(key, json.dumps(data, default=str))
#         r.expire(key, CACHE_TTL_SECONDS) 
#         query_text = data.get('query', '')
#         store_id = data.get('store_id', '')
#         query_hash = hashlib.md5(query_text.lower().encode()).hexdigest()[:12]
#         pattern_key = f"query_pattern:{query_hash}"
#         r.setex(pattern_key, SIMILARITY_CACHE_TTL, json.dumps({
#             'query': query_text,
#             'categories': data.get('all_generated_categories', []),
#             'timestamp': data.get('timestamp')
#         }, default=str))
#         store_query_key = f"store:{store_id}:frequent_queries"
#         r.zincrby(store_query_key, 1, query_hash)
#         r.expire(store_query_key, FREQUENT_CACHE_TTL)
#         user_prefs_key = f"user:{user_id}:preferences"
#         preferences = {
#             'recent_cuisines': data.get('cuisinebased', []),
#             'dietary_prefs': data.get('dietarypreferences', []),
#             'recent_dishes': data.get('dishbased', []),
#             'last_store': store_id,
#             'updated_at': datetime.now().isoformat()
#         }
#         r.setex(user_prefs_key, FREQUENT_CACHE_TTL, json.dumps(preferences, default=str))
#         logger.info(f"Data saved to Redis for user: {user_id} with 2-day TTL")
#         return True
#     except Exception as e:
#         logger.error(f"Error saving to Redis: {e}")
#         return False

# def get_user_queries_from_redis(user_id: str) -> list:
#     """Get all queries for a user"""
#     logger.info(f"Retrieving queries from Redis for user: {user_id}")
#     if not r:
#         logger.error("Redis not available")
#         return []
#     try:
#         key = f"user_id:{user_id}:queries"
#         queries = r.lrange(key, 0, -1)
#         if not queries:
#             logger.info(f"No queries found for user: {user_id}")
#             return []
#         parsed_queries = []
#         for query in queries:
#             try:
#                 parsed_queries.append(json.loads(query))
#             except json.JSONDecodeError as e:
#                 logger.error(f"Error parsing query JSON: {e}")
#                 continue
#         parsed_queries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
#         logger.info(f"Retrieved {len(parsed_queries)} queries for user: {user_id}")
#         return parsed_queries
#     except Exception as e:
#         logger.error(f"Error retrieving queries from Redis: {e}")
#         return []

# def get_cached_query_similarity(query: str, store_id: str) -> Optional[Dict]:
#     if not r:
#         return None
#     try:
#         query_hash = hashlib.md5(query.lower().encode()).hexdigest()[:12]
#         pattern_key = f"query_pattern:{query_hash}"
#         cached_data = r.get(pattern_key)
#         if cached_data:
#             logger.info(f"Found cached similarity for query hash: {query_hash}")
#             return json.loads(cached_data)
#         return None
#     except Exception as e:
#         logger.debug(f"Error checking query similarity cache: {e}")
#         return None

# def cache_product_matching_result(query: str, store_id: str, result: Dict):
#     if not r:
#         return
#     try:
#         cache_key = f"product_match:{hashlib.md5(f'{query}:{store_id}'.encode()).hexdigest()[:16]}"
#         r.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(result, default=str))
#         logger.info(f"Cached product matching result for query: {query[:30]}...")
#     except Exception as e:
#         logger.debug(f"Error caching product matching result: {e}")

# def get_cached_product_matching_result(query: str, store_id: str) -> Optional[Dict]:
#     if not r:
#         return None
#     try:
#         cache_key = f"product_match:{hashlib.md5(f'{query}:{store_id}'.encode()).hexdigest()[:16]}"
#         cached_result = r.get(cache_key)
#         if cached_result:
#             logger.info(f"Found cached product matching result for query: {query[:30]}...")
#             return json.loads(cached_result)
#         return None
#     except Exception as e:
#         logger.debug(f"Error retrieving cached product matching result: {e}")
#         return None

# def warm_cache_for_user(user_id: str, store_id: str):
#     if not r:
#         return
#     try:
#         user_prefs_key = f"user:{user_id}:preferences"
#         prefs_data = r.get(user_prefs_key)
#         if prefs_data:
#             preferences = json.loads(prefs_data)
#             recent_cuisines = preferences.get('recent_cuisines', [])
#             for cuisine in recent_cuisines[:2]:
#                 logger.info(f"Cache warming queued for cuisine: {cuisine}")
#         logger.info(f"Cache warming completed for user: {user_id}")
#     except Exception as e:
#         logger.debug(f"Error in cache warming: {e}")

# def maintain_cache():
#     if not r:
#         return
#     try:
#         logger.info("Cache maintenance completed")
#     except Exception as e:
#         logger.error(f"Error in cache maintenance: {e}")

# def get_cache_stats():
#     if not r:
#         return {}
#     try:
#         info = r.info('memory')
#         return {
#             'used_memory': info.get('used_memory_human'),
#             'max_memory': info.get('maxmemory_human'),
#             'memory_usage': info.get('used_memory_percentage', 0),
#             'connected_clients': r.info('clients').get('connected_clients', 0),
#             'cache_hit_ratio': 'N/A'
#         }
#     except Exception as e:
#         logger.error(f"Error getting cache stats: {e}")
#         return {}

# logger.info("Redis cache module loaded successfully")


import logging
logger = logging.getLogger(__name__)
logger.info("Redis module disabled - running without cache")
# Redis caching is currently disabled.