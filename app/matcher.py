import os
import pandas as pd
import logging
import json
from concurrent.futures import ThreadPoolExecutor
from rapidfuzz import process, fuzz
from app.utils import get_oid, normalize_mongo_id, safe_float
from app.core import assistant

# ---- LLM Imports and Initialization ----
from dotenv import load_dotenv
load_dotenv("apiky.env")
from langchain_openai import ChatOpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = "gpt-4o-mini"

llm = ChatOpenAI(
    model=LLM_MODEL,
    openai_api_key=OPENAI_API_KEY,
    temperature=0.2
)

logger = logging.getLogger(__name__)

# ---- LLM CACHING AND BATCHING FOR PERFORMANCE ----
llm_cache = {}

def batch_llm_validation_only(item_product_pairs, query_context=None):
    """
    ONLY batch LLM validation - NO individual calls
    Returns dict with (item, product) -> bool mapping.
    """
    if not item_product_pairs:
        return {}
    
    uncached_pairs = []
    results = {}
    
    # Check cache first
    for item, product_name, typical_use in item_product_pairs:
        cache_key = (item.lower(), product_name.lower(), typical_use.lower(), query_context or "")
        if cache_key in llm_cache:
            results[(item, product_name)] = llm_cache[cache_key]
        else:
            uncached_pairs.append((item, product_name, typical_use))
    
    if not uncached_pairs:
        return results
    context_line = f"User's cooking request: \"{query_context}\"\n\n" if query_context else ""
    
    batch_prompt = f'''{context_line}You are a strict culinary expert. For each ingredient-product pair below, determine if the product is TRULY suitable for the specific ingredient requested.

STRICT VALIDATION CRITERIA:
1. Exact ingredient match = YES
2. Same cuisine family = YES  
3. Different cuisine family = NO (unless fusion cooking mentioned)
4. Different food purpose = NO
5. Loosely related products = NO

Evaluate each pair:

'''
    
    for i, (item, product_name, typical_use) in enumerate(uncached_pairs, 1):
        batch_prompt += f"{i}. Ingredient: '{item}' → Product: '{product_name}' (Use: {typical_use})\n"
    
    batch_prompt += f"\nRespond ONLY in format: 1:YES, 2:NO, 3:YES, 4:NO, etc."
    
    try:
        resp = llm.invoke(batch_prompt)
        answer_text = resp.content if hasattr(resp, 'content') else str(resp)
        
        logger.info(f"Batch LLM validation completed for {len(uncached_pairs)} pairs in single API call")
        for line in answer_text.replace('\n', ',').split(','):
            if ':' in line:
                try:
                    idx_str, decision = line.strip().split(':', 1)
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(uncached_pairs):
                        item, product_name, typical_use = uncached_pairs[idx]
                        is_valid = decision.strip().upper().startswith('YES')
                        results[(item, product_name)] = is_valid
                        
                        # Cache result
                        cache_key = (item.lower(), product_name.lower(), typical_use.lower(), query_context or "")
                        llm_cache[cache_key] = is_valid
                        
                        status = "APPROVED" if is_valid else "REJECTED"
                        logger.debug(f"Batch validation: '{item}' → '{product_name}' = {status}")
                except (ValueError, IndexError):
                    continue
        for item, product_name, typical_use in uncached_pairs:
            if (item, product_name) not in results:
                results[(item, product_name)] = False
                cache_key = (item.lower(), product_name.lower(), typical_use.lower(), query_context or "")
                llm_cache[cache_key] = False
                
    except Exception as e:
        logger.error(f"Batch LLM validation error: {e}")
        for item, product_name, typical_use in uncached_pairs:
            results[(item, product_name)] = False
    
    return results

def smart_product_filtering(item, category_products, max_candidates=5):
    """
    Smart pre-filtering using ONLY algorithmic matching (no LLM calls)
    Returns top candidates based on scoring algorithm
    """
    item_clean = item.strip().lower()
    item_words = [w for w in item_clean.split() if len(w) > 2]
    
    candidates = []
    
    # Score each product algorithmically
    for product in category_products:
        product_name = product["ProductName"].lower().strip()
        main_ingredient = str(product.get("MainIngredient", "")).lower().strip()
    
        score = 0
        match_type = "none"
    
        # Exact substring match 
        if item_clean in product_name:
            score = 100
            match_type = "exact"
        
        # Word matching in product name 
        elif any(word in product_name for word in item_words):
            word_matches = sum(1 for word in item_words if word in product_name)
            score = 85 + (word_matches * 7)
            match_type = "word_match"
        
        # Main ingredient matching 
        elif main_ingredient and (item_clean in main_ingredient or any(word in main_ingredient for word in item_words)):
            score = 75  
            match_type = "ingredient"
        
        # Fuzzy matching 
        else:
            try:
                fuzzy_score = fuzz.partial_ratio(item_clean, product_name)
                if fuzzy_score >= 65: 
                    score = fuzzy_score
                    match_type = "fuzzy"
            except:
                pass
        
        # Only include products with meaningful scores
        if score >= 40:  
            candidates.append((product, score, match_type))
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:max_candidates]

def safe_percentage_to_float(val, fallback=0.0):
    """Convert percentage string to float (e.g., '18%' -> 18.0)"""
    if val is None:
        return fallback
    
    try:
        val_str = str(val).strip()
        if val_str.endswith('%'):
            return float(val_str[:-1])
        else:
            return safe_float(val, fallback)
    except (ValueError, TypeError):
        return fallback

def load_products():
    """Load products from Excel DataFrame with exact field names"""
    logger.info("Loading products from Excel DataFrame")
    try:
        if assistant.products_df is None:
            logger.error("Products DataFrame not available")
            return []
        
        products = []
        category_counts = {}
        
        for i, (_, row) in enumerate(assistant.products_df.iterrows()):
            sno = row.get("Sno", i + 1)
            mongo_id = normalize_mongo_id(f"product_{sno}")
            image_links = []
            if pd.notna(row.get("imagelink")):
                imagelink_str = str(row.get("imagelink", "")).strip()
                if imagelink_str:
                    image_links = [link.strip() for link in imagelink_str.split(",") if link.strip()]
            category_raw = row.get("category", "")
            category_name = str(category_raw).strip() if pd.notna(category_raw) and str(category_raw).lower() != 'nan' else "Unknown"
            
            normalized_product = {
                "_id": mongo_id, 
                # "ProductID": mongo_id, 
                "ProductName": str(row.get("ProductName", "")).strip(),
                "image": image_links,
                "category": category_name,
                "subCategory": str(row.get("subCategory", "")).strip(),
                "unit": str(row.get("unit", "")).strip(),
                "mrpPrice": safe_float(row.get("mrpPrice", 0)),
                "offerPrice": safe_float(row.get("offerPrice", 0)),
                "isGstInclusive": bool(row.get("isGstInclusive", False)),
                "gst": safe_percentage_to_float(row.get("gst", 0)),
                "barcode": str(row.get("barcode", "")).strip(),
                "hsncode": str(row.get("hsncode", "")).strip(),
                "startingUnit": safe_float(row.get("startingUnit", 0)),
                "endingUnit": safe_float(row.get("endingUnit", 0)),
                "MainIngredient": str(row.get("MainIngredient", "")).strip(),
                "TypicalUse": str(row.get("TypicalUse", "")).strip(),
                "quantity": 1
            }
            products.append(normalized_product)
            
            category_counts[category_name] = category_counts.get(category_name, 0) + 1
        
        logger.info(f"Successfully loaded {len(products)} products in {len(category_counts)} categories")
        return products
    except Exception as e:
        logger.error(f"Error loading products from Excel: {e}")
        return []

def match_products_with_ingredients(categories, query_context=None):
    """
    Product matching with ONLY batch LLM validation - NO individual LLM calls
    """
    logger.info(f"Starting product matching for {len(categories)} categories (BATCH LLM ONLY)")
    products_data = load_products()
    if not products_data:
        return []

    product_categories = {}
    for product in products_data:
        cat_name = product["category"]
        if cat_name and cat_name.lower() != 'nan' and cat_name != 'Unknown':
            if cat_name not in product_categories:
                product_categories[cat_name] = []
            product_categories[cat_name].append(product)
    
    logger.info(f"Available categories: {list(product_categories.keys())}")
    final_results = []
    
    for cat_entry in categories:
        try:
            category_data = cat_entry.get("category", {})
            input_category_name = category_data.get("name", "Unknown")
            items = cat_entry.get("items", [])
            
            logger.info(f"Processing category: '{input_category_name}' with {len(items)} items")
            matched_category = None
            for excel_cat_name in product_categories.keys():
                if input_category_name.lower().strip() == excel_cat_name.lower().strip():
                    matched_category = excel_cat_name
                    break
            
            if not matched_category:
                try:
                    excel_categories = list(product_categories.keys())
                    fuzzy_matches = process.extract(
                        input_category_name.lower().strip(), 
                        [cat.lower().strip() for cat in excel_categories], 
                        scorer=fuzz.ratio, 
                        limit=1
                    )
                    
                    if fuzzy_matches and len(fuzzy_matches[0]) >= 2:
                        match_name_lower, score = fuzzy_matches[0][0], fuzzy_matches[0][1]
                        if score >= 80:
                            for original_cat in excel_categories:
                                if original_cat.lower().strip() == match_name_lower:
                                    matched_category = original_cat
                                    break
                except Exception as e:
                    logger.warning(f"Error in fuzzy category matching: {e}")
            
            if not matched_category:
                logger.warning(f"No matching category found for: '{input_category_name}'")
                continue
            
            category_products = product_categories[matched_category]
            logger.info(f"Found {len(category_products)} products in category '{matched_category}'")
            all_validation_pairs = []
            item_candidate_map = {}
            
            for item in items:
                logger.info(f"Pre-filtering candidates for item: '{item}' (algorithmic only)")
                candidates = smart_product_filtering(item, category_products, max_candidates=5)
                
                if candidates:
                    logger.info(f"Found {len(candidates)} candidates for '{item}'")
                    item_candidate_map[item] = candidates
                    for product, score, match_type in candidates:
                        typical_use = product.get("TypicalUse", "")
                        all_validation_pairs.append((item, product["ProductName"], typical_use))
                else:
                    logger.info(f"No candidates found for '{item}'")
            if all_validation_pairs:
                logger.info(f"Performing SINGLE batch LLM validation for {len(all_validation_pairs)} candidates...")
                validation_results = batch_llm_validation_only(all_validation_pairs, query_context)
                logger.info(f"Batch validation completed with single API call!")
            else:
                validation_results = {}
            final_products = []
            seen_product_names = set()
            
            for item in items:
                if item in item_candidate_map:
                    for product, score, match_type in item_candidate_map[item]:
                        is_valid = validation_results.get((item, product["ProductName"]), False)
                        
                        if is_valid and product["ProductName"] not in seen_product_names:
                            mrp_price = safe_float(product["mrpPrice"], 0.0)
                            offer_price = safe_float(product["offerPrice"], 0.0)
                            
                            public_product = {
                                # "ProductID": product["ProductID"],  
                                "ProductName": product["ProductName"],
                                "image": product["image"],
                                "mrpPrice": mrp_price,
                                "offerPrice": offer_price,
                                "quantity": 1
                            }
                            final_products.append(public_product)
                            seen_product_names.add(product["ProductName"])
                            
                            logger.info(f"APPROVED: '{product['ProductName']}' for '{item}' ({match_type}, score: {score})")
                        elif not is_valid:
                            logger.info(f"REJECTED: '{product['ProductName']}' for '{item}' (failed LLM validation)")
            if final_products:
                category_result = {
                    "category": category_data,
                    "products": final_products
                }
                final_results.append(category_result)
                logger.info(f"SUCCESS: Category '{input_category_name}' -> {len(final_products)} validated products")
            else:
                logger.warning(f"No valid products found for category '{input_category_name}' after validation")
                
        except Exception as e:
            logger.error(f"Error processing category '{input_category_name}': {e}")
            continue
    
    logger.info(f"FINAL RESULT: {len(final_results)} categories with validated matches")
    return final_results

def match_products_with_ingredients_for_redis(categories, query_context=None):
    """Match products for Redis storage - same structure as public API now"""
    logger.info("Matching products for Redis storage (BATCH LLM ONLY)")
    return match_products_with_ingredients(categories, query_context=query_context)
