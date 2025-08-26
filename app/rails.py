import re
from typing import List, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

class ValidationRails:
    """Validation and guardrails for grocery assistant operations"""
    
    MAX_QUERY_LENGTH = 1000
    MAX_USER_ID_LENGTH = 100
    MAX_STORE_ID_LENGTH = 100
    
    BLOCKED_PATTERNS = [
        r'<script.*?>.*?</script>',
        r'javascript:',
        r'data:text/html',
        r'vbscript:',
        r'onload=',
        r'onerror=',
    ]
    
    @classmethod
    def validate_query(cls, query: str) -> Tuple[bool, str]:
        """Validate user query input"""
        if not query or not isinstance(query, str):
            return False, "Query is required and must be a string"
        
        query = query.strip()
        
        if len(query) == 0:
            return False, "Query cannot be empty"
        
        if len(query) > cls.MAX_QUERY_LENGTH:
            return False, f"Query too long (max {cls.MAX_QUERY_LENGTH} characters)"
        
        for pattern in cls.BLOCKED_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                logger.warning(f"Blocked query pattern detected: {pattern}")
                return False, "Query contains invalid content"
        
        return True, "Valid"
    
    @classmethod
    def validate_user_id(cls, user_id: str) -> Tuple[bool, str]:
        """Validate user ID"""
        if not user_id or not isinstance(user_id, str):
            return False, "User ID is required and must be a string"
        
        user_id = user_id.strip()
        
        if len(user_id) == 0:
            return False, "User ID cannot be empty"
        
        if len(user_id) > cls.MAX_USER_ID_LENGTH:
            return False, f"User ID too long (max {cls.MAX_USER_ID_LENGTH} characters)"

        if not re.match(r'^[a-zA-Z0-9_-]+$', user_id):
            return False, "User ID can only contain letters, numbers, hyphens, and underscores"
        
        return True, "Valid"
    
    @classmethod
    def validate_store_id(cls, store_id: str) -> Tuple[bool, str]:
        """Validate store ID (MongoDB ObjectId format)"""
        if not store_id or not isinstance(store_id, str):
            return False, "Store ID is required and must be a string"
        
        store_id = store_id.strip()
        
        if len(store_id) == 0:
            return False, "Store ID cannot be empty"
        
        if len(store_id) > cls.MAX_STORE_ID_LENGTH:
            return False, f"Store ID too long (max {cls.MAX_STORE_ID_LENGTH} characters)"

        if not re.match(r'^[a-fA-F0-9]{24}$', store_id):
            return False, "Store ID must be a valid MongoDB ObjectId (24 hexadecimal characters)"
        
        return True, "Valid"
    
    @classmethod
    def sanitize_product_results(cls, results: List[Dict]) -> List[Dict]:
        """Sanitize product matching results"""
        sanitized = []
        
        for category_result in results[:100]: 
            if isinstance(category_result, dict) and "category" in category_result and "products" in category_result:
                products = category_result["products"]
                if isinstance(products, list):
                    clean_products = []
                    for product in products[:100]:  
                        if isinstance(product, dict) and "ProductName" in product:
                            clean_products.append(product)
                    
                    if clean_products:
                        sanitized.append({
                            "category": category_result["category"],
                            "products": clean_products
                        })
        
        return sanitized

validation_rails = ValidationRails()
