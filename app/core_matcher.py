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

logger = logging.getLogger(__name__)
load_dotenv(dotenv_path="config.env")

class CoreMatcher:
    def __init__(self):
        logger.info("Initializing CoreMatcher with MongoDB data")
        self.llm = None
        self.validation_llm = None
        self.llm_cache = {}
        self._init_llm()
        logger.info("CoreMatcher initialized successfully")

    def _init_llm(self):
        """Initialize OpenAI LLM"""
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set in environment")
            
            self.llm = ChatOpenAI(model="gpt-4o-mini", openai_api_key=api_key, temperature=0.2)
            self.validation_llm = ChatOpenAI(model="gpt-4o-mini", openai_api_key=api_key, temperature=0.2)
            logger.info("OpenAI LLM initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing LLM: {e}")
            raise ValueError(f"Failed to initialize LLM: {e}")

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
            logger.error(f"Response content: {cleaned_content}")
            raise
        except Exception as e:
            logger.error(f"Error extracting JSON: {e}")
            raise

    def generate_ingredients_and_match_products(self, user_query: str, store_id: str):
        """
        Enhanced product matching - returns both all_generated_categories and matched_products
        """
        logger.info(f"Processing query: '{user_query[:50]}...' for store: {store_id}")
        available_categories = get_categories_by_store(store_id)
        if not available_categories:
            logger.warning(f"No categories found for store: {store_id}")
            return {
                "all_generated_categories": [],
                "matched_products": []
            }
        
        logger.info(f"Available categories for store {store_id}: {[cat['name'] for cat in available_categories]}")
        ingredients_data = self._generate_ingredients_llm(user_query, available_categories)
        if not ingredients_data:
            logger.warning("No ingredients generated from LLM")
            return {
                "all_generated_categories": [],
                "matched_products": []
            }
        
        logger.info(f"Generated ingredient categories: {[cat.get('category', 'Unknown') for cat in ingredients_data]}")
        all_generated_categories = []
        for category_data in ingredients_data:
            category_name = category_data.get("category", "").strip()
            items = category_data.get("items", [])
            
            if category_name and items:
                # Find category info
                category_info = self._find_matching_category(category_name, available_categories)
                if category_info:
                    all_generated_categories.append({
                        "category": {
                            "_id": category_info["_id"],
                            "categoryId": category_info.get("categoryId", category_info["_id"]),
                            "name": category_info["name"]
                        },
                        "items": items
                    })
                else:
                    all_generated_categories.append({
                        "category": {
                            "_id": "UNKNOWN",
                            "categoryId": "UNKNOWN",
                            "name": category_name
                        },
                        "items": items
                    })
        matched_products = []
        
        for category_data in ingredients_data:
            try:
                category_name = category_data.get("category", "").strip()
                items = category_data.get("items", [])
                
                if not category_name or not items:
                    logger.warning(f"Skipping invalid category data: {category_data}")
                    continue
                
                logger.info(f"Processing category: '{category_name}' with items: {items}")
                
                # Find the category info
                category_info = self._find_matching_category(category_name, available_categories)
                
                if not category_info:
                    logger.warning(f"Category '{category_name}' not found in available categories - skipping product matching")
                    continue
                
                logger.info(f"Matched category '{category_name}' to '{category_info['name']}' (ID: {category_info['_id']})")
                
                # Get optimized products for fuzzy matching
                products = get_optimized_products_for_matching(category_info['name'], store_id)
                if not products:
                    logger.warning(f"No products found for category '{category_info['name']}' and store {store_id}")
                    continue
                
                logger.info(f"Found {len(products)} optimized products for category '{category_info['name']}'")
                matched_category_products = self._enhanced_match_and_validate_products(items, products, user_query)
                
                if matched_category_products:
                    matched_products.append({
                        "category": {
                            "_id": category_info["_id"],
                            "categoryId": category_info.get("categoryId", category_info["_id"]),
                            "name": category_info["name"]
                        },
                        "products": matched_category_products
                    })
                    logger.info(f"Successfully matched {len(matched_category_products)} products for category '{category_info['name']}'")
                else:
                    logger.warning(f"No products matched after validation for category '{category_info['name']}'")
            
            except Exception as e:
                logger.error(f"Error processing category {category_data}: {e}")
                continue
        
        logger.info(f"Successfully processed query - Generated categories: {len(all_generated_categories)}, Matched categories: {len(matched_products)}")
        
        return {
            "all_generated_categories": all_generated_categories,
            "matched_products": matched_products
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
        
        logger.warning(f"No matching category found for '{category_name}' in available categories: {[cat['name'] for cat in available_categories]}")
        return None

    def _generate_ingredients_llm(self, user_query: str, available_categories: list):
        """Generate ingredients using LLM"""
        try:
            category_list = "\n".join([f'- {cat["name"]}' for cat in available_categories])
            
            prompt = f'''You are a culinary expert. Analyze this cooking request and suggest ingredients by category.

User request: "{user_query}"

Available Categories (ONLY use these):
{category_list}

IMPORTANT:
- ONLY use category names EXACTLY as provided in the list above
- Match ingredients to the specific dish/cuisine mentioned
- Focus on commonly used ingredients for the requested dish
- Consider real-world cooking practices

Response format (JSON only):
{{
  "categories": [
    {{
      "category": "<exact category name from list>",
      "items": ["item1", "item2", "item3"]
    }}
  ]
}}

Respond with ONLY the JSON structure above:'''
            
            response = self.llm.invoke(prompt)
            result = self._extract_json_from_response(response.content)
            
            if not isinstance(result, dict) or "categories" not in result:
                logger.error(f"Invalid LLM response structure: {result}")
                raise ValueError("Invalid response structure")
            
            categories = result["categories"]
            logger.info(f"Generated {len(categories)} ingredient categories")
            return categories
            
        except Exception as e:
            logger.error(f"Error generating ingredients: {e}")
            return []

    def _enhanced_match_and_validate_products(self, items: list, products: list, user_query: str):
        """Enhanced product matching with optimized fuzzy matching"""
        try:
            logger.info(f"Starting enhanced matching for {len(items)} items against {len(products)} products")
            all_matched_products = self._get_matching_products_for_items(items, products)
            
            if not all_matched_products:
                logger.warning("No products matched using enhanced fuzzy matching")
                return []
            
            logger.info(f"Found {len(all_matched_products)} candidate products after fuzzy matching")
            validation_pairs = []
            for product_info in all_matched_products:
                validation_pairs.append((product_info["matched_item"], product_info["ProductName"]))
            validation_results = self._batch_llm_validation(validation_pairs, user_query)
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
                    
                    logger.info(f"APPROVED: '{product_name}' for '{item}' (score: {product_info.get('match_score', 0)})")
                elif not is_valid:
                    logger.debug(f"REJECTED: '{product_name}' for '{item}' (failed LLM validation)")
            
            logger.info(f"Final products after LLM validation: {len(final_products)}")
            return final_products
            
        except Exception as e:
            logger.error(f"Error in enhanced match and validate: {e}")
            return []

    def _get_matching_products_for_items(self, items: list, products: list):
        """Core function to match products against generated items using enhanced fuzzy matching"""
        matched_products = []
        used_product_ids = set()
        for item in items:
            logger.info(f"Matching products for item: '{item}'")
            
            item_matches = self._robust_fuzzy_match_single_item(item, products)
            
            # Add unique matches
            for product, score in item_matches:
                product_id = str(product["_id"])
                if product_id not in used_product_ids:
                    matched_products.append({
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
                    
                    logger.debug(f"Added match: '{product['ProductName']}' for '{item}' (score: {score})")
        matched_products.sort(key=lambda x: x["match_score"], reverse=True)
        
        logger.info(f"Total unique products matched: {len(matched_products)}")
        return matched_products

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
        """
        Robust fuzzy matching with image URL matching and proper sorting
        """
        try:
            if not item or not products:
                return []
            
            item_clean = item.strip().lower()
            item_words = [w for w in item_clean.split() if len(w) > 2]
            matches = []
            
            for i, product in enumerate(products):
                try:
                    # Validate product structure
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
                    try:
                        fuzzy_name_score = fuzz.partial_ratio(item_clean, product_name_lower)
                        if fuzzy_name_score > max_score and fuzzy_name_score >= threshold:
                            max_score = fuzzy_name_score
                            match_source = "fuzzy_name"
                    except Exception:
                        pass
                    images = product.get("image", [])
                    if isinstance(images, list) and images:
                        for image_url in images:
                            if isinstance(image_url, str):
                                filename = self._extract_filename_from_url(image_url)
                                if filename:
                                    if item_clean in filename:
                                        image_score = 95
                                        if image_score > max_score:
                                            max_score = image_score
                                            match_source = "exact_image"
                                    elif any(word in filename for word in item_words if word):
                                        word_count = sum(1 for word in item_words if word and word in filename)
                                        image_score = 80 + (word_count * 3)
                                        if image_score > max_score:
                                            max_score = min(image_score, 95)
                                            match_source = "word_image"
                                    else:
                                        try:
                                            fuzzy_image_score = fuzz.partial_ratio(item_clean, filename)
                                            if fuzzy_image_score > max_score and fuzzy_image_score >= (threshold - 10):
                                                max_score = fuzzy_image_score
                                                match_source = "fuzzy_image"
                                        except Exception:
                                            pass
                    if max_score >= threshold:
                        matches.append({
                            'product': product,
                            'score': max_score,
                            'source': match_source,
                            'index': i  
                        })
                        
                        logger.debug(f"Match found: '{product_name}' for '{item}' (score: {max_score}, source: {match_source})")
                
                except Exception as product_error:
                    logger.debug(f"Error processing product {i}: {product_error}")
                    continue
            try:
                matches.sort(key=lambda x: (-x['score'], x['index']))
            except Exception as sort_error:
                logger.error(f"Error sorting matches: {sort_error}")
                return []
            result = []
            for match in matches[:100]: 
                result.append((match['product'], match['score']))
            
            logger.debug(f"Robust fuzzy matching for '{item}': found {len(result)} matches")
            return result
            
        except Exception as e:
            logger.error(f"Error in robust fuzzy matching for item '{item}': {e}")
            return []

    def _batch_llm_validation(self, item_product_pairs: list, query_context: str):
        """Batch validate product-item suitability with LLM"""
        if not item_product_pairs or not self.validation_llm:
            return {}
        
        uncached_pairs = []
        results = {}
        for item, product_name in item_product_pairs:
            cache_key = (item.lower(), product_name.lower(), query_context.lower())
            if cache_key in self.llm_cache:
                results[(item, product_name)] = self.llm_cache[cache_key]
            else:
                uncached_pairs.append((item, product_name))
        
        if not uncached_pairs:
            return results
        prompt = f'''You are a strict culinary expert. User wants to cook: "{query_context}"

For each ingredient-product pair, determine if the product is TRULY suitable for the ingredient in this dish context.

STRICT CRITERIA:
1. Exact ingredient match = YES
2. Same cuisine family = YES  
3. Different cuisine family = NO
4. Real-world cooking compatibility = YES/NO

Evaluate each pair:

'''
        
        for i, (item, product_name) in enumerate(uncached_pairs, 1):
            prompt += f"{i}. Ingredient: '{item}' → Product: '{product_name}'\n"
        
        prompt += f"\nRespond ONLY in format: 1:YES, 2:NO, 3:YES, 4:NO, etc."
        
        try:
            resp = self.validation_llm.invoke(prompt)
            answer_text = resp.content if hasattr(resp, 'content') else str(resp)
            
            logger.info(f"Batch LLM validation completed for {len(uncached_pairs)} pairs")
            
            for line in answer_text.replace('\n', ',').split(','):
                if ':' in line:
                    try:
                        idx_str, decision = line.strip().split(':', 1)
                        idx = int(idx_str) - 1
                        if 0 <= idx < len(uncached_pairs):
                            item, product_name = uncached_pairs[idx]
                            is_valid = decision.strip().upper().startswith('YES')
                            results[(item, product_name)] = is_valid
                            cache_key = (item.lower(), product_name.lower(), query_context.lower())
                            self.llm_cache[cache_key] = is_valid
                    except (ValueError, IndexError) as e:
                        logger.debug(f"Error parsing LLM response line '{line}': {e}")
                        continue
            for item, product_name in uncached_pairs:
                if (item, product_name) not in results:
                    results[(item, product_name)] = False
                    
        except Exception as e:
            logger.error(f"Batch LLM validation error: {e}")
            for item, product_name in uncached_pairs:
                results[(item, product_name)] = False
        
        return results

    def infer_metadata(self, user_query: str):
        """Generate metadata for Redis storage"""
        try:
            prompt = f'''Analyze this query and extract metadata.

Query: "{user_query}"

Response format (JSON only):
{{
  "dishbased": ["dish_name"],
  "cuisinebased": ["cuisine_type"],
  "dietarypreferences": ["Vegan", "Vegetarian", "Non-Vegetarian"],
  "timebased": ["breakfast", "lunch", "dinner", "snack"]
}}

Respond with ONLY the JSON structure above:'''
            
            response = self.llm.invoke(prompt)
            result = self._extract_json_from_response(response.content)
            
            return {
                "dishbased": result.get("dishbased", ["general"]),
                "cuisinebased": result.get("cuisinebased", ["international"]),
                "dietarypreferences": result.get("dietarypreferences", ["mixed"]),
                "timebased": result.get("timebased", ["general"])
            }
            
        except Exception as e:
            logger.error(f"Error inferring metadata: {e}")
            return {
                "dishbased": ["general"],
                "cuisinebased": ["international"],
                "dietarypreferences": ["mixed"],
                "timebased": ["general"]
            }

# Global instance
core_matcher = CoreMatcher()
