import json
import logging
from rapidfuzz import process, fuzz
from app.utils import get_oid, normalize_mongo_id, safe_float

logger = logging.getLogger(__name__)

def load_products():
    """Load products from JSON file"""
    logger.info("Loading products from JSON file")
    
    try:
        with open("asset/products.json", "r", encoding="utf-8") as f:
            raw_products = json.load(f)
        
        products = []
        category_counts = {}
        
        for i, product in enumerate(raw_products):
            raw_category_id = product.get("category")
            category_id = get_oid(raw_category_id)
            
            normalized_product = {
                "_id": normalize_mongo_id(product.get("_id")),
                "ProductName": product.get("ProductName", "").strip(),
                "image": product.get("image", []),
                "category": category_id,
                "mrpPrice": safe_float(product.get("mrpPrice", 0)),
                "offerPrice": safe_float(product.get("offerPrice", 0)),
                "quantity": 1
            }
            products.append(normalized_product)
            category_counts[category_id] = category_counts.get(category_id, 0) + 1
            
            if i < 3:
                logger.debug(f"Sample Product {i+1}: '{product.get('ProductName', '')[:50]}'")
        
        logger.info(f"Successfully loaded {len(products)} products in {len(category_counts)} categories")
        return products
        
    except Exception as e:
        logger.error(f"Error loading products: {e}")
        return []

def match_products_with_ingredients(categories):
    """Match ingredients to products - returns response WITH category _id"""
    logger.info(f"Starting product matching for {len(categories)} categories")
    
    products_data = load_products()
    if not products_data:
        return []
    
    # Create category lookup
    product_categories = {}
    for product in products_data:
        cat_id = product["category"]
        if cat_id not in product_categories:
            product_categories[cat_id] = []
        product_categories[cat_id].append(product)
    
    final_results = []

    for cat_entry in categories:
        try:
            category_data = cat_entry.get("category", {})
            
            # Extract category ID for matching
            raw_cat_id = None
            for id_field in ["_id", "id", "mongo_id"]:
                if id_field in category_data:
                    raw_cat_id = category_data[id_field]
                    break
            
            if not raw_cat_id:
                continue
            
            cat_id = get_oid(raw_cat_id)
            cat_name = category_data.get("name", "Unknown")
            items = cat_entry.get("items", [])
            
            logger.info(f"Processing category: '{cat_name}' (ID: {cat_id})")
            
            if cat_id not in product_categories:
                logger.warning(f"No products found for category: {cat_name}")
                continue
            
            category_products = product_categories[cat_id]
            matched_products = []
            
            # Match items to products
            for item in items:
                item_clean = item.strip().lower()
                item_matches = []
                
                # Substring matching
                for product in category_products:
                    product_name = product["ProductName"].lower().strip()
                    
                    if item_clean in product_name:
                        item_matches.append((product, 100, "direct"))
                        continue
                    
                    # Word matching
                    item_words = [w for w in item_clean.split() if len(w) > 2]
                    if item_words:
                        product_words = product_name.split()
                        word_matches = sum(1 for iw in item_words for pw in product_words if iw in pw or pw in iw)
                        if word_matches > 0:
                            score = (word_matches / len(item_words)) * 80
                            item_matches.append((product, score, "word"))
                
                # Fuzzy matching
                if len(item_matches) < 2:
                    try:
                        product_names = [p["ProductName"].lower().strip() for p in category_products]
                        fuzzy_matches = process.extract(item_clean, product_names, scorer=fuzz.partial_ratio, limit=3)
                        
                        for match_result in fuzzy_matches:
                            if len(match_result) >= 2:
                                match_name, score = match_result[0], match_result[1]
                                if score >= 30:
                                    product = next((p for p in category_products if p["ProductName"].lower().strip() == match_name), None)
                                    if product:
                                        item_matches.append((product, score, "fuzzy"))
                    except Exception:
                        pass
                
                # Add best matches
                if item_matches:
                    unique_matches = {}
                    for product, score, method in item_matches:
                        prod_name = product["ProductName"]
                        if prod_name not in unique_matches or unique_matches[prod_name][1] < score:
                            unique_matches[prod_name] = (product, score, method)
                    
                    sorted_matches = sorted(unique_matches.values(), key=lambda x: x[1], reverse=True)
                    
                    for product, score, method in sorted_matches[:3]:
                        public_product = {
                            "ProductName": product["ProductName"],
                            "image": product["image"],
                            "mrpPrice": product["mrpPrice"],
                            "offerPrice": product["offerPrice"],
                            "quantity": 1
                        }
                        
                        if public_product not in matched_products:
                            matched_products.append(public_product)
                            logger.info(f"  Added: {product['ProductName']} (score: {score})")
            
            # Add to results - INCLUDES category _id
            if matched_products:
                category_result = {
                    "category": {
                        "_id": normalize_mongo_id(cat_id),  # INCLUDES _id
                        "name": cat_name
                    },
                    "products": matched_products  # Products still without _id for privacy
                }
                final_results.append(category_result)
                logger.info(f"SUCCESS: Category '{cat_name}' -> {len(matched_products)} products")
                
        except Exception as e:
            logger.error(f"Error processing category: {e}")
            continue
    
    logger.info(f"FINAL RESULT: {len(final_results)} categories with matches")
    return final_results

def match_products_with_ingredients_for_redis(categories):
    """Match products and return with FULL IDs for Redis storage - FIXED"""
    logger.info("Matching products for Redis storage (with internal IDs)")
    
    products_data = load_products()
    if not products_data:
        return []
    
    results_with_ids = []
    public_results = match_products_with_ingredients(categories)
    
    for result in public_results:
        products_with_ids = []
        
        for public_product in result["products"]:
            # Find the original product with _id
            original_product = next(
                (p for p in products_data 
                 if p["ProductName"] == public_product["ProductName"]),
                None
            )
            
            if original_product:
                # FIXED: Remove category field from product storage
                product_with_id = {
                    "_id": original_product["_id"],
                    "ProductName": original_product["ProductName"],
                    "image": original_product["image"],
                    "mrpPrice": original_product["mrpPrice"],
                    "offerPrice": original_product["offerPrice"],
                    "quantity": 1
                    # Removed category field - not needed in Redis storage
                }
                products_with_ids.append(product_with_id)
        
        # Keep same category structure as public response
        result_with_ids = {
            "category": result["category"],  # Already has _id
            "products": products_with_ids     # Now includes product _id for Redis, no category field
        }
        results_with_ids.append(result_with_ids)
    
    return results_with_ids
