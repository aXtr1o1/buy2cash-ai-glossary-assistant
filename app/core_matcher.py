import logging
import os
import json
import re
from datetime import datetime
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from rapidfuzz import fuzz, process
from app.db import get_categories_by_store, get_optimized_products_for_matching
from app.utils import safe_float
import urllib.parse
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from typing import Dict, List, Tuple, Any
from functools import lru_cache
import threading

logger = logging.getLogger(__name__)
load_dotenv(dotenv_path="config.env")

class OptimizedCoreMatcher:
    def __init__(self):
        logger.info("Initializing CoreMatcher with advanced caching")
        self.llm = None
        self.validation_llm = None
        self.llm_cache = {}
        self.similarity_cache = {}
        self.product_cache = {}
        self.category_cache = {}
        self.cache_lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=6)
        self._init_llm()
        logger.info("CoreMatcher initialized successfully")

    def _init_llm(self):
        """Initialize OpenAI LLM with optimized settings"""
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set in environment")

            self.llm = ChatOpenAI(
                model="gpt-4o-mini", 
                openai_api_key=api_key, 
                temperature=0.3,
                max_retries=2,
                request_timeout=30
            )
            self.validation_llm = ChatOpenAI(
                model="gpt-4o-mini", 
                openai_api_key=api_key, 
                temperature=0.2,
                max_retries=2,
                request_timeout=20
            )
            logger.info("OpenAI LLM initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing LLM: {e}")
            raise ValueError(f"Failed to initialize LLM: {e}")

    async def generate_ingredients_and_match_products_async(self, user_query: str, store_id: str):
        """
        Fully async product matching with parallel processing
        """
        start_time = time.time()
        logger.info(f"Starting ASYNC processing: '{user_query[:50]}...' for store: {store_id}")
        async def get_categories_async():
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(self.executor, get_categories_by_store, store_id)
        
        available_categories = await get_categories_async()
        
        if not available_categories:
            logger.warning(f"No categories found for store: {store_id}")
            return {"all_generated_categories": [], "matched_products": []}
        
        prep_time = time.time() - start_time
        logger.info(f"Data preparation completed in {prep_time:.2f}s")
        llm_start = time.time()
        ingredients_data = await self._generate_ingredients_llm_async(user_query, available_categories)
        llm_time = time.time() - llm_start
        logger.info(f"LLM ingredient generation completed in {llm_time:.2f}s")
        
        if not ingredients_data:
            logger.warning("No ingredients generated from LLM")
            return {"all_generated_categories": [], "matched_products": []}
        matching_start = time.time()
        matching_tasks = []
        for category_data in ingredients_data:
            task = asyncio.create_task(
                self._process_category_parallel(category_data, available_categories, store_id, user_query)
            )
            matching_tasks.append(task)
        category_results = await asyncio.gather(*matching_tasks, return_exceptions=True)
        
        matching_time = time.time() - matching_start
        logger.info(f"Parallel category matching completed in {matching_time:.2f}s")
        
        all_generated_categories = []
        matched_products = []
        
        for i, result in enumerate(category_results):
            if isinstance(result, Exception):
                logger.error(f"Error processing category {i}: {result}")
                continue
            
            if result and isinstance(result, dict):
                if result.get('generated_category'):
                    all_generated_categories.append(result['generated_category'])
                if result.get('matched_category'):
                    matched_products.append(result['matched_category'])
        
        total_time = time.time() - start_time
        logger.info(f"ASYNC processing completed in {total_time:.2f}s - Generated: {len(all_generated_categories)}, Matched: {len(matched_products)}")
        
        return {
            "all_generated_categories": all_generated_categories,
            "matched_products": matched_products
        }

    async def _process_category_parallel(self, category_data: dict, available_categories: list, store_id: str, user_query: str):
        """Process single category"""
        try:
            category_name = category_data.get("category", "").strip()
            items = category_data.get("items", [])
            
            if not category_name or not items:
                return None
            
            category_info = self._find_matching_category(category_name, available_categories)
            
            generated_category = {
                "category": {
                    "_id": category_info["_id"] if category_info else "UNKNOWN",
                    "categoryId": category_info.get("categoryId", "UNKNOWN") if category_info else "UNKNOWN",
                    "name": category_info["name"] if category_info else category_name
                },
                "items": items
            }
            
            if not category_info:
                logger.warning(f"Category '{category_name}' not found - skipping product matching")
                return {"generated_category": generated_category, "matched_category": None}
            
            loop = asyncio.get_event_loop()
            products = await loop.run_in_executor(
                self.executor, 
                get_optimized_products_for_matching, 
                category_info['name'], 
                store_id
            )
            
            if not products:
                logger.warning(f"No products found for category '{category_info['name']}'")
                return {"generated_category": generated_category, "matched_category": None}
            
            matched_products = await self._enhanced_match_and_validate_products_async(
                items, products, user_query
            )
            
            if matched_products:
                matched_category = {
                    "category": {
                        "_id": category_info["_id"],
                        "categoryId": category_info.get("categoryId", category_info["_id"]),
                        "name": category_info["name"]
                    },
                    "products": matched_products
                }
                return {"generated_category": generated_category, "matched_category": matched_category}
            
            return {"generated_category": generated_category, "matched_category": None}
            
        except Exception as e:
            logger.error(f"Error in parallel category processing: {e}")
            return None

    async def _generate_ingredients_llm_async(self, user_query: str, available_categories: list):
        """Async LLM generation with comprehensive supermarket coverage"""
        try:
            category_list = "\n".join([f'- {cat["name"]}' for cat in available_categories])
            prompt = f'''You are a comprehensive SuperMarket expert with deep knowledge of ALL supermarket departments and items.

User request: "{user_query}"

Available Categories (ONLY use these exact names):
{category_list}

COMPREHENSIVE ANALYSIS REQUIRED:
- Consider the complete shopping experience for this request
- Include preparation tools, storage items, cleaning supplies if relevant  
- Think about complementary items and alternatives
- Consider dietary restrictions, cultural preferences, seasonal availability
- Include both essential and optional items for the best experience
- Think about quantity, storage, and meal planning needs

Response format (JSON only):
{{
  "categories": [
    {{
      "category": "<exact category name from list>",
      "items": ["essential_item1", "essential_item2", "optional_item3", "alternative_item4"]
    }}
  ]
}}

IMPORTANT: Use ONLY category names exactly as listed above. Consider ALL possible supermarket items that would enhance the user's experience.
If he asked an specific product (e.g., "olive oil"), include related items (e.g., "vinegar", "salad dressing", "marinade") in the same or related categories.
Sometimes, user will ask like with the specific product name (e.g., "Achi sambar masala") and return that specific product in the relevant category.
Respond with ONLY the JSON structure above:'''

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(self.executor, self.llm.invoke, prompt)
            
            result = self._extract_json_from_response(response.content)
            
            if not isinstance(result, dict) or "categories" not in result:
                logger.error(f"Invalid LLM response structure: {result}")
                raise ValueError("Invalid response structure")
            
            categories = result["categories"]
            logger.info(f"Generated {len(categories)} comprehensive ingredient categories")
            return categories
            
        except Exception as e:
            logger.error(f"Error in async ingredient generation: {e}")
            return []

    async def _enhanced_match_and_validate_products_async(self, items: list, products: list, user_query: str):
        """Fully async product matching with parallel validation"""
        try:
            logger.info(f"Starting async enhanced matching for {len(items)} items against {len(products)} products")
            loop = asyncio.get_event_loop()
            
            matching_tasks = []
            for item in items:
                task = loop.run_in_executor(
                    self.executor,
                    self._robust_fuzzy_match_single_item,
                    item, products, 60
                )
                matching_tasks.append(task)
            item_matches = await asyncio.gather(*matching_tasks)
            all_matched_products = []
            used_product_ids = set()
            
            for i, item in enumerate(items):
                matches = item_matches[i]
                for product, score in matches:
                    product_id = str(product["_id"])
                    if product_id not in used_product_ids:
                        all_matched_products.append({
                            "Product_id": product_id,
                            "ProductName": product["ProductName"],
                            "image": product.get("image", []),
                            "mrpPrice": safe_float(product.get("mrpPrice"), 0.0),
                            "offerPrice": safe_float(product.get("offerPrice"), 0.0),
                            "quantity": 1,
                            "match_score": score,
                            "matched_item": item
                        })
                        used_product_ids.add(product_id)
            
            if not all_matched_products:
                logger.warning("No products matched using enhanced fuzzy matching")
                return []
            
            logger.info(f"Found {len(all_matched_products)} candidate products after parallel fuzzy matching")
            validation_pairs = [(p["matched_item"], p["ProductName"]) for p in all_matched_products]
            validation_results = await self._batch_llm_validation_async(validation_pairs, user_query)
            final_products = []
            seen_products = set()
            
            for product_info in all_matched_products:
                item = product_info["matched_item"]
                product_name = product_info["ProductName"]
                
                is_valid = validation_results.get((item, product_name), False)
                
                if is_valid and product_name not in seen_products:
                    final_product = {
                        "Product_id": product_info["Product_id"],
                        "ProductName": product_name,
                        "image": product_info["image"],
                        "mrpPrice": product_info["mrpPrice"],
                        "offerPrice": product_info["offerPrice"],
                        "quantity": 1
                    }
                    final_products.append(final_product)
                    seen_products.add(product_name)
            
            logger.info(f"Final products after async LLM validation: {len(final_products)}")
            return final_products
            
        except Exception as e:
            logger.error(f"Error in async enhanced match and validate: {e}")
            return []

    async def _batch_llm_validation_async(self, item_product_pairs: list, query_context: str):
        """Async batch LLM validation with intelligent caching"""
        if not item_product_pairs or not self.validation_llm:
            return {}
        uncached_pairs = []
        results = {}
        
        with self.cache_lock:
            for item, product_name in item_product_pairs:
                cache_key = (item.lower(), product_name.lower(), query_context.lower()[:50])
                if cache_key in self.llm_cache:
                    results[(item, product_name)] = self.llm_cache[cache_key]
                else:
                    uncached_pairs.append((item, product_name))
        
        if not uncached_pairs:
            return results
        batch_size = 25
        batch_tasks = []
        
        for i in range(0, len(uncached_pairs), batch_size):
            batch = uncached_pairs[i:i + batch_size]
            task = self._process_validation_batch_async(batch, query_context)
            batch_tasks.append(task)
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        for batch_result in batch_results:
            if isinstance(batch_result, dict):
                results.update(batch_result)
        with self.cache_lock:
            for item, product_name in uncached_pairs:
                if (item, product_name) in results:
                    cache_key = (item.lower(), product_name.lower(), query_context.lower()[:50])
                    self.llm_cache[cache_key] = results[(item, product_name)]
        
        return results

    async def _process_validation_batch_async(self, batch_pairs: list, query_context: str):
        """Process a single validation batch asynchronously"""
        try:
            prompt = f"""
You are a strict supermarket product matching expert. Your task is to filter out any product that is not a **real-world, practical** match for the user's actual intent.

User Request Context: "{query_context}"

**STRICT VALIDATION CRITERIA:**

Respond **YES** ONLY if the product is:
- An exact ingredient match for this specific request, OR
- The best practical substitute for the request, OR
- Something commonly used together with the main dish/cuisine mentioned

Respond **NO** if the product is:
- Different cuisine family or cooking style
- Not a real ingredient or tool needed for this request
- Not commonly used in this context
- Any reasonable doubt about real-world relevance

**IMPORTANT:** If you are unsure about any item, choose NO.

Validate each pair:
"""
            
            for i, (item, product_name) in enumerate(batch_pairs, 1):
                prompt += f"{i}. '{item}' -> '{product_name}'\n"
            
            prompt += f"\nRespond format: 1:YES, 2:NO, 3:YES, 4:NO"
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(self.executor, self.validation_llm.invoke, prompt)
            
            answer_text = resp.content if hasattr(resp, 'content') else str(resp)
            results = {}
            for line in answer_text.replace('\n', ',').split(','):
                if ':' in line:
                    try:
                        idx_str, decision = line.strip().split(':', 1)
                        idx = int(idx_str) - 1
                        if 0 <= idx < len(batch_pairs):
                            item, product_name = batch_pairs[idx]
                            is_valid = decision.strip().upper().startswith('YES')
                            results[(item, product_name)] = is_valid
                    except (ValueError, IndexError):
                        continue
            for item, product_name in batch_pairs:
                if (item, product_name) not in results:
                    results[(item, product_name)] = False
            
            return results
            
        except Exception as e:
            logger.error(f"Batch validation error: {e}")
            return {(item, product_name): False for item, product_name in batch_pairs}

    async def infer_metadata_async(self, user_query: str):
        """Async metadata generation"""
        try:
            prompt = f'''Analyze and extract metadata from this query.

Query: "{user_query}"

Response format (JSON only):
{{
  "dishbased": ["specific_dish_name"],
  "cuisinebased": ["cuisine_type"],
  "dietarypreferences": ["dietary_type"],
  "timebased": ["meal_time"]
}}

Instructions:
- dishbased: Main dish/recipe mentioned (e.g., "biryani", "pasta", "salad")
- cuisinebased: Cuisine type (e.g., "Indian", "Italian", "Chinese", "International")
- dietarypreferences: Diet type (e.g., "Vegetarian", "Non-Vegetarian", "Vegan", "Mixed")
- timebased: Meal timing (e.g., "breakfast", "lunch", "dinner", "snack", "general")

Provide exactly one relevant value for each field.
Respond with ONLY the JSON:'''
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(self.executor, self.llm.invoke, prompt)
            
            result = self._extract_json_from_response(response.content)
            
            return {
                "dishbased": result.get("dishbased", ["general"]),
                "cuisinebased": result.get("cuisinebased", ["international"]),
                "dietarypreferences": result.get("dietarypreferences", ["mixed"]),
                "timebased": result.get("timebased", ["general"])
            }
            
        except Exception as e:
            logger.error(f"Error in async metadata inference: {e}")
            return {
                "dishbased": ["general"],
                "cuisinebased": ["international"],
                "dietarypreferences": ["mixed"],
                "timebased": ["general"]
            }

    def _find_matching_category(self, category_name: str, available_categories: list):
        """Find matching category with improved fuzzy matching"""
        if not category_name or not available_categories:
            return None
        
        category_name_lower = category_name.lower().strip()
        for cat in available_categories:
            if cat["name"].lower().strip() == category_name_lower:
                return cat
        for cat in available_categories:
            cat_name_lower = cat["name"].lower().strip()
            if category_name_lower in cat_name_lower or cat_name_lower in category_name_lower:
                return cat

        variations = [
            category_name_lower,
            category_name_lower.replace(" ", ""),
            category_name_lower.replace("&", "and"),
            category_name_lower.replace("and", "&"),
            category_name_lower.replace("s", "").rstrip(),
        ]
        
        for cat in available_categories:
            cat_name_lower = cat["name"].lower().strip()
            for variation in variations:
                if variation in cat_name_lower or cat_name_lower in variation:
                    return cat
        
        logger.warning(f"No matching category found for '{category_name}'")
        return None

    def _extract_json_from_response(self, response_content: str):
        """Extract JSON from LLM response content"""
        try:
            cleaned_content = response_content.strip()
            if cleaned_content.startswith('```'):
                cleaned_content = cleaned_content[7:]
            elif cleaned_content.startswith('```'):
                cleaned_content = cleaned_content[3:]
            if cleaned_content.endswith('```'):
                cleaned_content = cleaned_content[:-3]
            cleaned_content = cleaned_content.strip()
            
            json_pattern = r'\{.*\}'
            match = re.search(json_pattern, cleaned_content, re.DOTALL)
            
            if match:
                return json.loads(match.group(0))
            return json.loads(cleaned_content)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decoding failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Error extracting JSON: {e}")
            raise

    def _extract_filename_from_url(self, url: str):
        """Extract filename from image URL for matching"""
        try:
            if not url or not isinstance(url, str):
                return ""

            parsed_url = urllib.parse.urlparse(url)
            filename = os.path.basename(parsed_url.path)
            filename_without_ext = os.path.splitext(filename)
            clean_filename = filename_without_ext.replace('-', ' ').replace('_', ' ').replace('.', ' ')
            clean_filename = ' '.join(clean_filename.split()) 
            
            return clean_filename.lower()
            
        except Exception as e:
            logger.debug(f"Error extracting filename from URL {url}: {e}")
            return ""

    def _robust_fuzzy_match_single_item(self, item: str, products: list, threshold: int = 60):
        """Robust fuzzy matching with image URL matching"""
        try:
            if not item or not products:
                return []
            
            item_clean = item.strip().lower()
            item_words = [w for w in item_clean.split() if len(w) > 2]
            matches = []
            
            for i, product in enumerate(products):
                try:
                    if not isinstance(product, dict) or not product.get("ProductName"):
                        continue
                    
                    product_name = str(product["ProductName"]).strip()
                    if not product_name:
                        continue
                    
                    product_name_lower = product_name.lower()
                    max_score = 0
                    match_source = "none"
                    if item_clean in product_name_lower:
                        max_score = 100
                        match_source = "exact_name"
                    elif any(word in product_name_lower for word in item_words if word):
                        word_count = sum(1 for word in item_words if word and word in product_name_lower)
                        score = 85 + (word_count * 5)
                        if score > max_score:
                            max_score = min(score, 100)
                            match_source = "word_name"
                    if max_score < 90:
                        try:
                            fuzzy_name_score = fuzz.partial_ratio(item_clean, product_name_lower)
                            if fuzzy_name_score > max_score and fuzzy_name_score >= threshold:
                                max_score = fuzzy_name_score
                                match_source = "fuzzy_name"
                        except Exception:
                            pass
                    if max_score < 95:
                        images = product.get("image", [])
                        if isinstance(images, list) and images:
                            for image_url in images[:10]:  
                                if isinstance(image_url, str):
                                    filename = self._extract_filename_from_url(image_url)
                                    if filename:
                                        if item_clean in filename:
                                            image_score = 95
                                            if image_score > max_score:
                                                max_score = image_score
                                                match_source = "exact_image"
                                                break
                    
                    if max_score >= threshold:
                        matches.append({
                            'product': product,
                            'score': max_score,
                            'source': match_source,
                            'index': i
                        })
                
                except Exception as product_error:
                    logger.debug(f"Error processing product {i}: {product_error}")
                    continue
            
            matches.sort(key=lambda x: (-x['score'], x['index']))
            
            result = [(match['product'], match['score']) for match in matches[:50]]
            return result
            
        except Exception as e:
            logger.error(f"Error in robust fuzzy matching for item '{item}': {e}")
            return []

# Global optimized instance
core_matcher = OptimizedCoreMatcher()
