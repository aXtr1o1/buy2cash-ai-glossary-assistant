import logging
from typing import List, Dict, Union, Any, Optional
from pydantic import BaseModel, Field, validator, RootModel

logger = logging.getLogger(__name__)

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
    #ProductID: Optional[Union[Dict[str, str], str]] 
    ProductName: str
    image: List[str] = Field(default_factory=list)
    mrpPrice: float
    offerPrice: float
    quantity: int = 1

class CategoryProductList(BaseModel):
    category: SlimCategory  
    products: List[Product]  

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

class GenerationResponse(BaseModel):
    user_id: str
    query: str
    timestamp: str
    categories: List[IngredientCategory]

class ProductMappingResponse(RootModel[List[CategoryProductList]]):
    root: List[CategoryProductList]

class ProductInternal(BaseModel):
    #ProductID: Optional[Union[Dict[str, str], str]] 
    ProductName: str
    image: List[str] = Field(default_factory=list)
    mrpPrice: float
    offerPrice: float
    quantity: int = 1

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
