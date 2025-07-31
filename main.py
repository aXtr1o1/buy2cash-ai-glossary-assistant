import logging
from fastapi import FastAPI
from app.api import router

# Configure logging to save in app.log file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log", mode='a'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Buy2Cash Grocery AI Assistant", version="1.0.0")
app.include_router(router)

@app.on_event("startup")
async def startup_event():
    logger.info("Buy2Cash Grocery AI Assistant started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Buy2Cash Grocery AI Assistant shutting down")

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)

    
#To run the application, use the command:
# uvicorn main:app --reload