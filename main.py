import logging
from fastapi import FastAPI
from app.api import router
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log", mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)
app = FastAPI(
    title="Buy2Cash Optimized Grocery AI Assistant",
    version="1.0.0",
    description="Glrocery product matching with AI"
)

app.include_router(router)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "optimizations": [
            "async_processing",
            "parallel_matching", 
            "2_day_cache",
            "enhanced_prompts"
        ]
    }

@app.on_event("startup")
async def startup_event():
    logger.info("Buy2Cash Optimized Grocery AI Assistant started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Buy2Cash Grocery AI Assistant shutting down")

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting optimized server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
