import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from app.core import assistant
from app.matcher import match_products_with_ingredients, match_products_with_ingredients_for_redis
from app.redis_cache import save_to_redis, get_user_queries
from app.schemas import (
    GenerateRequest, 
    MatchRequest,
    GenerationResponse,
    ProductMappingResponse,
    SlimCategory,
    UserQueriesResponse
)
from typing import List

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/categories", response_model=List[SlimCategory])
async def get_categories():
    """Get all available categories"""
    logger.info("GET /categories endpoint called")
    try:
        categories = assistant.categories_list
        logger.info(f"Returning {len(categories)} categories")
        return categories
    except Exception as e:
        logger.error(f"Error in get_categories: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate", response_model=GenerationResponse)
async def generate_ingredients(request: GenerateRequest):
    """Generate ingredients from user query"""
    logger.info(f"POST /generate endpoint called for user: {request.user_id}")
    logger.debug(f"Query: '{request.query}'")
    
    try:
        result = assistant.generate_ingredients(request.query)
        
        response = {
            "user_id": request.user_id,
            "query": request.query,
            "timestamp": result["timestamp"],
            "categories": result["categories"]
        }
        
        logger.info(f"Successfully generated ingredients for user: {request.user_id}")
        return response
        
    except Exception as e:
        logger.error(f"Error in generate_ingredients: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/match", response_model=ProductMappingResponse)
async def match_products(request: MatchRequest):
    """Match ingredients to products"""
    logger.info(f"POST /match endpoint called for user: {request.user_id}")
    logger.debug(f"Matching {len(request.categories)} categories")
    
    try:
        # Convert to dict for processing
        categories_dict = [cat.dict() for cat in request.categories]
        
        # Get product matches (public version)
        matched_results = match_products_with_ingredients(categories_dict)
        
        # Get version with internal IDs for Redis storage
        matched_results_with_ids = match_products_with_ingredients_for_redis(categories_dict)
        
        # Generate metadata with better error handling
        logger.info("Generating metadata for Redis storage...")
        metadata = assistant.infer_metadata(request.query)
        logger.info(f"Generated metadata: {metadata}")
        
        # Use proper timestamp - either from request or current time
        current_timestamp = request.timestamp if hasattr(request, 'timestamp') and request.timestamp else datetime.now().isoformat()
        
        # Save to Redis with product results and proper timestamp
        redis_data = {
            "user_id": request.user_id,
            "query": request.query,
            "timestamp": current_timestamp,  # FIXED: Use proper timestamp
            "product_mapping_results": matched_results_with_ids,  # FIXED: Use version with product IDs
            "dishbased": metadata.get("dishbased", []),
            "cuisinebased": metadata.get("cuisinebased", []),
            "dietarypreferences": metadata.get("dietarypreferences", []),
            "timebased": metadata.get("timebased", [])
        }
        
        logger.info(f"Saving to Redis: timestamp={current_timestamp}, metadata keys present: {list(metadata.keys())}")
        save_to_redis(request.user_id, redis_data)
        
        logger.info(f"Successfully matched products for user: {request.user_id}")
        return matched_results  # Return public version without product IDs
        
    except Exception as e:
        logger.error(f"Error in match_products: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/queries/{user_id}", response_model=UserQueriesResponse)
async def get_user_queries_endpoint(user_id: str):
    """Get user search history with metadata"""
    logger.info(f"GET /queries/{user_id} endpoint called")
    
    try:
        queries = get_user_queries(user_id)
        if not queries:
            logger.warning(f"No queries found for user: {user_id}")
            raise HTTPException(status_code=404, detail="No queries found")
        
        logger.info(f"Returning {len(queries)} queries for user: {user_id}")
        return {"queries": queries}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_user_queries_endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "data_source": "json",
        "categories_loaded": len(assistant.categories_list),
        "timestamp": datetime.now().isoformat()
    }
