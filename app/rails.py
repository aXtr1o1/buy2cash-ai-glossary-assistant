"""
Guardrails and validation logic for the grocery assistant
Ensures data quality and prevents malicious inputs
"""

import re
from typing import List, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

class ValidationRails:
    """Validation and guardrails for grocery assistant operations"""
    
    # Maximum limits to prevent abuse
    MAX_QUERY_LENGTH = 1000
    MAX_CATEGORIES_PER_QUERY = 10
    MAX_ITEMS_PER_CATEGORY = 20
    MAX_USER_ID_LENGTH = 100
    
    # Blocked patterns (case insensitive)
    BLOCKED_PATTERNS = [
        r'<script.*?>.*?</script>',  # XSS protection
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
        
        # Check for blocked patterns
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
        
        # Basic alphanumeric validation
        if not re.match(r'^[a-zA-Z0-9_-]+$', user_id):
            return False, "User ID can only contain letters, numbers, hyphens, and underscores"
        
        return True, "Valid"
    
    @classmethod
    def validate_categories_structure(cls, categories: List[Dict]) -> Tuple[bool, str]:
        """Validate categories structure from LLM or user input"""
        if not isinstance(categories, list):
            return False, "Categories must be a list"
        
        if len(categories) > cls.MAX_CATEGORIES_PER_QUERY:
            return False, f"Too many categories (max {cls.MAX_CATEGORIES_PER_QUERY})"
        
        for i, cat_entry in enumerate(categories):
            if not isinstance(cat_entry, dict):
                return False, f"Category {i} must be an object"
            
            if "category" not in cat_entry:
                return False, f"Category {i} missing 'category' field"
            
            if "items" not in cat_entry:
                return False, f"Category {i} missing 'items' field"
            
            items = cat_entry["items"]
            if not isinstance(items, list):
                return False, f"Category {i} items must be a list"
            
            if len(items) > cls.MAX_ITEMS_PER_CATEGORY:
                return False, f"Category {i} has too many items (max {cls.MAX_ITEMS_PER_CATEGORY})"
            
            # Validate individual items
            for j, item in enumerate(items):
                if not isinstance(item, str) or not item.strip():
                    return False, f"Category {i}, item {j} must be a non-empty string"
        
        return True, "Valid"
    
    @classmethod
    def sanitize_llm_response(cls, response: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize LLM response to ensure data quality"""
        sanitized = {}
        
        # Handle categories
        categories = response.get("categories", [])
        if isinstance(categories, list):
            sanitized_categories = []
            for cat_entry in categories[:cls.MAX_CATEGORIES_PER_QUERY]:  # Limit categories
                if isinstance(cat_entry, dict) and "category" in cat_entry and "items" in cat_entry:
                    items = cat_entry["items"]
                    if isinstance(items, list):
                        # Clean and limit items
                        clean_items = []
                        for item in items[:cls.MAX_ITEMS_PER_CATEGORY]:
                            if isinstance(item, str) and item.strip():
                                clean_item = item.strip()[:100]  # Limit item length
                                clean_items.append(clean_item)
                        
                        sanitized_categories.append({
                            "category": cat_entry["category"],
                            "items": clean_items
                        })
            
            sanitized["categories"] = sanitized_categories
        
        # Handle metadata arrays
        for field in ["dishbased", "cuisinebased", "dietarypreferences", "timebased"]:
            value = response.get(field, [])
            if isinstance(value, list):
                # Clean and limit metadata
                clean_values = []
                for v in value[:5]:  # Limit to 5 items per metadata field
                    if isinstance(v, str) and v.strip():
                        clean_v = v.strip().lower()[:50]  # Limit length and normalize
                        if re.match(r'^[a-zA-Z0-9\s_-]+$', clean_v):  # Only alphanumeric
                            clean_values.append(clean_v)
                
                sanitized[field] = clean_values
            else:
                sanitized[field] = []
        
        return sanitized

# Global instance for easy access
validation_rails = ValidationRails()
