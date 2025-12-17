import logging
from typing import List, Dict, Union, Any, Optional
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

class Category(BaseModel):
    _id: str
    categoryId: str  
    name: str

class Seller(BaseModel):
    _id: str
    sellerId: str  
    storeName: str
    storeContactName: str
    email: Optional[str] = ""
    phoneNumber: Optional[str] = ""
    status: str
    isActive: bool

class IngredientCategory(BaseModel):
    category: Category
    items: List[str]

class ProductMatch(BaseModel):
    Product_id: str
    ProductName: str
    image: List[str] = Field(default_factory=list)
    mrpPrice: float
    offerPrice: float
    quantity: int = 1

class CategoryProductMatch(BaseModel):
    category: Category
    products: List[ProductMatch]

class ProductMatchingRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    user_id: str = Field(..., min_length=1, max_length=100)
    store_id: str = Field(..., min_length=1, max_length=100)
    
    @field_validator('query')
    @classmethod
    def validate_query(cls, v):
        return v.strip()
    
    @field_validator('user_id')
    @classmethod
    def validate_user_id(cls, v):
        return v.strip()
    
    @field_validator('store_id')
    @classmethod
    def validate_store_id(cls, v):
        return v.strip()

class ProductMatchingResponse(BaseModel):
    query: str
    user_id: str
    store_id: str
    timestamp: str
    matched_products: List[CategoryProductMatch]

# class RedisStoreData(BaseModel):
#     user_id: str
#     store_id: str
#     query: str
#     timestamp: str
#     all_generated_categories: List[IngredientCategory] = Field(default_factory=list) 
#     matched_products: List[CategoryProductMatch]  
#     dishbased: List[str] = Field(default_factory=list)
#     cuisinebased: List[str] = Field(default_factory=list)
#     dietarypreferences: List[str] = Field(default_factory=list)
#     timebased: List[str] = Field(default_factory=list)

# class UserQueriesResponse(BaseModel):
#     queries: List[RedisStoreData]

logger.info("schemas loaded successfully")
