import logging
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path="config.env")

logger = logging.getLogger(__name__)
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB_NAME")
if not MONGO_URI:
    raise ValueError("MONGO_URI not found in config.env file")
if not DB_NAME:
    raise ValueError("MONGO_DB_NAME not found in config.env file")

logger.info(f"Using MONGO_URI: {MONGO_URI}")
logger.info(f"Using DB_NAME: {DB_NAME}")

try:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    client.admin.command('ping')
    logger.info(f"Successfully connected to MongoDB: {DB_NAME}")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    raise

def get_all_categories():
    """Fetch all categories with _id, categoryId and name"""
    try:
        categories = list(db.categories.find({}, {"_id": 1, "name": 1}))
        result = []
        for cat in categories:
            result.append({
                "_id": str(cat["_id"]),
                "categoryId": str(cat["_id"]), 
                "name": cat["name"]
            })
        logger.info(f"Retrieved {len(result)} categories from MongoDB")
        return result
    except Exception as e:
        logger.error(f"Error fetching categories: {e}")
        return []

def get_all_sellers():
    """Fetch all sellers/stores with basic info including sellerId"""
    try:
        sellers = list(db.sellers.find({}, {
            "_id": 1, 
            "storeName": 1, 
            "storeContactName": 1,
            "email": 1,
            "phoneNumber": 1,
            "status": 1,
            "isActive": 1
        }))
        
        result = []
        for seller in sellers:
            result.append({
                "_id": str(seller["_id"]),
                "sellerId": str(seller["_id"]),  
                "storeName": seller.get("storeName", ""),
                "storeContactName": seller.get("storeContactName", ""),
                "email": seller.get("email", ""),
                "phoneNumber": seller.get("phoneNumber", ""),
                "status": seller.get("status", ""),
                "isActive": seller.get("isActive", False)
            })
        
        logger.info(f"Retrieved {len(result)} sellers from MongoDB")
        return result
    except Exception as e:
        logger.error(f"Error fetching sellers: {e}")
        return []

def get_categories_by_store(store_id: str):
    """Fetch categories that have products from a specific store including categoryId"""
    try:
        store_oid = ObjectId(store_id)
        category_oids = db.products.distinct("category", {"seller": store_oid})
        
        if not category_oids:
            logger.warning(f"No categories found for store: {store_id}")
            return []
        categories = list(db.categories.find(
            {"_id": {"$in": category_oids}}, 
            {"_id": 1, "name": 1}
        ))
        
        result = []
        for cat in categories:
            result.append({
                "_id": str(cat["_id"]),
                "categoryId": str(cat["_id"]),  
                "name": cat["name"]
            })
        
        logger.info(f"Retrieved {len(result)} categories for store {store_id}")
        return result
        
    except Exception as e:
        logger.error(f"Error fetching categories for store {store_id}: {e}")
        return []

def get_optimized_products_for_matching(category_name: str, store_id: str):
    """Enhanced database query to fetch products optimized for fuzzy matching"""
    try:
        store_oid = ObjectId(store_id)
        category = db.categories.find_one({"name": category_name})
        if not category:
            logger.warning(f"Category '{category_name}' not found")
            return []
        
        category_oid = category["_id"]
        logger.info(f"Found category '{category_name}' with ID: {category_oid}")
        products = list(db.products.find({
            "category": category_oid,
            "seller": store_oid,
            "status": "APPROVED",  
            "stage": "ACTIVATE",   
            "ProductName": {"$exists": True, "$ne": "", "$ne": None}  
        }, {
            "_id": 1,
            "ProductName": 1,
            "image": 1,
            "mrpPrice": 1,
            "offerPrice": 1,
            "posPrice": 1,
            "stockQuantity": 1,
            "availabilityStatus": 1
        }))
        filtered_products = []
        for p in products:
            product_name = p.get("ProductName", "")
            if isinstance(product_name, str) and product_name.strip():
                product = {
                    "_id": str(p["_id"]),
                    "ProductName": product_name.strip(),
                    "image": p.get("image", []),
                    "mrpPrice": float(p.get("mrpPrice", 0)),
                    "offerPrice": float(p.get("offerPrice", 0)),
                    "posPrice": float(p.get("posPrice", 0)),
                    "stockQuantity": p.get("stockQuantity", 0),
                    "availabilityStatus": p.get("availabilityStatus", False)
                }
                filtered_products.append(product)
        
        logger.info(f"Retrieved {len(filtered_products)} valid products for category '{category_name}' and store {store_id}")
        return filtered_products
        
    except Exception as e:
        logger.error(f"Error fetching optimized products for category {category_name} and store {store_id}: {e}")
        return []

def get_products_by_category_and_store(category_name: str, store_id: str):
    """Legacy function - now uses optimized approach"""
    return get_optimized_products_for_matching(category_name, store_id)

def get_store_by_id(store_id: str):
    """Fetch store details by ID including sellerId"""
    try:
        store_oid = ObjectId(store_id)
        store = db.sellers.find_one({"_id": store_oid})
        
        if store:
            return {
                "_id": str(store["_id"]),
                "sellerId": str(store["_id"]),  
                "storeName": store.get("storeName", ""),
                "storeContactName": store.get("storeContactName", ""),
                "email": store.get("email", ""),
                "phoneNumber": store.get("phoneNumber", ""),
                "status": store.get("status", ""),
                "isActive": store.get("isActive", False)
            }
        else:
            logger.warning(f"Store not found: {store_id}")
            return None
            
    except Exception as e:
        logger.error(f"Error fetching store {store_id}: {e}")
        return None

def test_connection():
    """Test database connection and basic queries"""
    try:
        categories_count = db.categories.count_documents({})
        logger.info(f"Categories collection has {categories_count} documents")
        products_count = db.products.count_documents({})
        logger.info(f"Products collection has {products_count} documents")
        sellers_count = db.sellers.count_documents({})
        logger.info(f"Sellers collection has {sellers_count} documents")
        
        return True
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False
