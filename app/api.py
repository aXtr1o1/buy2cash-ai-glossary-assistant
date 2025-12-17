import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.concurrency import run_in_threadpool
from app.core_matcher import core_matcher
# from app.redis_cache import save_user_query_to_redis, get_user_queries_from_redis
from app.db import get_all_categories, get_all_sellers, get_store_by_id
from app.schemas import (
    ProductMatchingRequest,
    ProductMatchingResponse,
    Category,
    Seller,
    # UserQueriesResponse,
    # RedisStoreData
)
from app.rails import validation_rails
# from app.background_tasks import warm_cache_for_user_background
from typing import List
import time

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/categories", response_model=List[Category])
async def get_categories():
    """Get all available categories"""
    logger.info("GET /categories endpoint called")
    try:
        categories = await run_in_threadpool(get_all_categories)
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
        sellers = await run_in_threadpool(get_all_sellers)
        logger.info(f"Returning {len(sellers)} sellers")
        return sellers
    except Exception as e:
        logger.error(f"Error in get_sellers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ProductMatching", response_model=ProductMatchingResponse)
async def product_matching(request: ProductMatchingRequest, background_tasks: BackgroundTasks):
    """
    ProductMatching endpoint with async processing
    """
    start_time = time.time()
    logger.info(f"ProductMatching called for user: {request.user_id}, store: {request.store_id}")
    valid_query, query_msg = validation_rails.validate_query(request.query)
    if not valid_query:
        raise HTTPException(status_code=400, detail=query_msg)
    
    valid_uid, uid_msg = validation_rails.validate_user_id(request.user_id)
    if not valid_uid:
        raise HTTPException(status_code=400, detail=uid_msg)
    
    valid_store, store_msg = validation_rails.validate_store_id(request.store_id)
    if not valid_store:
        raise HTTPException(status_code=400, detail=store_msg)
    
    store = await run_in_threadpool(get_store_by_id, request.store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    try:
        logger.info("Starting ASYNC ingredient generation and product matching...")
        result = await core_matcher.generate_ingredients_and_match_products_async(
            request.query, 
            request.store_id
        )

        all_generated_categories = result.get("all_generated_categories", [])
        matched_products = result.get("matched_products", [])
        sanitized_results = await run_in_threadpool(validation_rails.sanitize_product_results, matched_products)
        # metadata = await core_matcher.infer_metadata_async(request.query)
        
        current_timestamp = datetime.now().isoformat()
        # redis_data = RedisStoreData(
        #     user_id=request.user_id,
        #     store_id=request.store_id,
        #     query=request.query,
        #     timestamp=current_timestamp,
        #     all_generated_categories=all_generated_categories,  
        #     matched_products=sanitized_results, 
        #     **metadata
        # )
        # background_tasks.add_task(save_user_query_to_redis, request.user_id, redis_data.model_dump())
        # background_tasks.add_task(warm_cache_for_user_background, request.user_id, request.store_id)
        
        response = ProductMatchingResponse(
            query=request.query,
            user_id=request.user_id,
            store_id=request.store_id,
            timestamp=current_timestamp,
            matched_products=sanitized_results
        )

        end_time = time.time()
        processing_time = end_time - start_time
        logger.info(f"processing completed in {processing_time:.2f}s - Generated: {len(all_generated_categories)}, Matched: {len(sanitized_results)}")
        
        return response

    except Exception as e:
        logger.error(f"Error in product matching: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# @router.get("/redis/{user_id}", response_model=UserQueriesResponse)
# async def get_user_queries(user_id: str):
#     """Get user search history from Redis"""
#     logger.info(f"GET /redis/{user_id} endpoint called")
    
#     valid_uid, uid_msg = validation_rails.validate_user_id(user_id)
#     if not valid_uid:
#         raise HTTPException(status_code=400, detail=uid_msg)
    
#     try:
#         queries = await run_in_threadpool(get_user_queries_from_redis, user_id)
#         return {"queries": queries if queries else []}
        
#     except Exception as e:
#         logger.error(f"Error retrieving user queries: {e}")
#         raise HTTPException(status_code=500, detail=str(e))
