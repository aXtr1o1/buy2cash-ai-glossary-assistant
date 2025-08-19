import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from app.core_matcher import core_matcher
from app.redis_cache import save_user_query_to_redis, get_user_queries_from_redis
from app.db import get_all_categories, get_all_sellers, get_store_by_id
from app.schemas import (
    ProductMatchingRequest,
    ProductMatchingResponse,
    Category,
    Seller,
    UserQueriesResponse,
    RedisStoreData,
    IngredientCategory
)
from app.rails import validation_rails
from typing import List

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/categories", response_model=List[Category])
async def get_categories():
    """Get all available categories"""
    logger.info("GET /categories endpoint called")
    try:
        categories = get_all_categories()
        logger.info(f"Returning {len(categories)} categories")
        return categories
    except Exception as e:
        logger.error(f"Error in get_categories: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sellers", response_model=List[Seller])
async def get_sellers():
    """Get all available sellers/stores"""
    logger.info("GET /sellers endpoint called")
    try:
        sellers = get_all_sellers()
        logger.info(f"Returning {len(sellers)} sellers")
        return sellers
    except Exception as e:
        logger.error(f"Error in get_sellers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ProductMatching", response_model=ProductMatchingResponse)
async def product_matching(request: ProductMatchingRequest):
    """
    Enhanced ProductMatching endpoint that:
    1. Returns query, user_id, store_id in response
    2. Saves ALL generated categories to Redis (not just matched ones)
    3. Returns formatted product matches
    """
    logger.info(f"ProductMatching called for user: {request.user_id}, store: {request.store_id}")
    logger.debug(f"Query: '{request.query}'")
    valid_query, query_msg = validation_rails.validate_query(request.query)
    if not valid_query:
        logger.warning(f"Invalid query: {query_msg}")
        raise HTTPException(status_code=400, detail=query_msg)

    valid_uid, uid_msg = validation_rails.validate_user_id(request.user_id)
    if not valid_uid:
        logger.warning(f"Invalid user_id: {uid_msg}")
        raise HTTPException(status_code=400, detail=uid_msg)
    
    valid_store, store_msg = validation_rails.validate_store_id(request.store_id)
    if not valid_store:
        logger.warning(f"Invalid store_id: {store_msg}")
        raise HTTPException(status_code=400, detail=store_msg)
    store = get_store_by_id(request.store_id)
    if not store:
        logger.warning(f"Store not found: {request.store_id}")
        raise HTTPException(status_code=404, detail="Store not found")
    
    logger.info(f"Processing for store: {store['storeName']} ({request.store_id})")

    try:
        logger.info("Starting ingredient generation and product matching...")
        result = core_matcher.generate_ingredients_and_match_products(
            request.query, 
            request.store_id
        )

        all_generated_categories = result.get("all_generated_categories", [])
        matched_products = result.get("matched_products", [])

        if not matched_products:
            logger.warning("No products matched for the query")
        logger.info("Applying guardrails to results...")
        sanitized_results = validation_rails.sanitize_product_results(matched_products)
        logger.info("Generating metadata...")
        metadata = core_matcher.infer_metadata(request.query)
        current_timestamp = datetime.now().isoformat()
        redis_data = RedisStoreData(
            user_id=request.user_id,
            store_id=request.store_id,
            query=request.query,
            timestamp=current_timestamp,
            all_generated_categories=all_generated_categories,  
            matched_products=sanitized_results, 
            **metadata
        )
        
        logger.info("Saving to Redis with ALL generated categories...")
        save_user_query_to_redis(request.user_id, redis_data.model_dump())
        response = ProductMatchingResponse(
            query=request.query,
            user_id=request.user_id,
            store_id=request.store_id,
            timestamp=current_timestamp,
            matched_products=sanitized_results
        )

        logger.info(f"Successfully processed query - Generated categories: {len(all_generated_categories)}, Matched categories: {len(sanitized_results)}")
        return response

    except Exception as e:
        logger.error(f"Error in product matching: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/redis/{user_id}", response_model=UserQueriesResponse)
async def get_user_queries(user_id: str):
    """Get user search history from Redis (includes ALL generated categories)"""
    logger.info(f"GET /redis/{user_id} endpoint called")
    valid_uid, uid_msg = validation_rails.validate_user_id(user_id)
    if not valid_uid:
        raise HTTPException(status_code=400, detail=uid_msg)
    
    try:
        queries = get_user_queries_from_redis(user_id)
        if not queries:
            logger.warning(f"No queries found for user: {user_id}")
            return {"queries": []}
        
        logger.info(f"Returning {len(queries)} queries for user: {user_id}")
        return {"queries": queries}
        
    except Exception as e:
        logger.error(f"Error retrieving user queries: {e}")
        raise HTTPException(status_code=500, detail=str(e))
