import logging
from typing import List, Dict, Union, Any
from pydantic import BaseModel, Field, validator, RootModel

logger = logging.getLogger(__name__)

# Public category model (includes _id for frontend usage)
class SlimCategory(BaseModel):
    _id: Union[Dict[str, str], str]
    name: str
    
    class Config:
        allow_population_by_field_name = True
        extra = "allow"

class IngredientCategory(BaseModel):
    category: SlimCategory
    items: List[str]
    
    class Config:
        extra = "allow"

class Product(BaseModel):
    ProductName: str
    image: List[str] = Field(default_factory=list)
    mrpPrice: float
    offerPrice: float
    quantity: int = 1

# Public response (includes category _id)
class CategoryProductList(BaseModel):
    category: SlimCategory  # Includes _id for frontend
    products: List[Product]  # Products still without _id for privacy

# Request Models
class GenerateRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    user_id: str = Field(..., min_length=1, max_length=100)
    
    @validator('query')
    def validate_query(cls, v):
        return v.strip()
    
    @validator('user_id')
    def validate_user_id(cls, v):
        return v.strip()

class MatchRequest(BaseModel):
    categories: List[IngredientCategory]
    user_id: str = Field(..., min_length=1, max_length=100)
    query: str = Field(..., min_length=1, max_length=1000)
    timestamp: str = None
    
    class Config:
        extra = "allow"

# Response Models
class GenerationResponse(BaseModel):
    user_id: str
    query: str
    timestamp: str
    categories: List[IngredientCategory]

# Public API response (includes category _id)
class ProductMappingResponse(RootModel[List[CategoryProductList]]):
    root: List[CategoryProductList]

# Internal models for Redis storage - FIXED
class ProductInternal(BaseModel):
    _id: Union[Dict[str, str], str]
    ProductName: str
    image: List[str] = Field(default_factory=list)
    mrpPrice: float
    offerPrice: float
    quantity: int = 1
    # Removed category field - not needed in Redis product storage

class CategoryProductListWithProductIds(BaseModel):
    category: SlimCategory
    products: List[ProductInternal]

class RedisMetadataResponse(BaseModel):
    user_id: str
    query: str
    timestamp: str
    product_mapping_results: List[CategoryProductListWithProductIds]
    dishbased: List[str] = Field(default_factory=list)
    cuisinebased: List[str] = Field(default_factory=list)
    dietarypreferences: List[str] = Field(default_factory=list)
    timebased: List[str] = Field(default_factory=list)

class UserQueriesResponse(BaseModel):
    queries: List[RedisMetadataResponse]

logger.info("Schemas loaded successfully")
