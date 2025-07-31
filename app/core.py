import pandas as pd
import os
import logging
import re
import json
from datetime import datetime
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from fastapi import HTTPException
from app.utils import normalize_mongo_id

logger = logging.getLogger(__name__)
load_dotenv(dotenv_path="config.env")

class GroceryAssistant:
    def __init__(self):
        logger.info("Initializing GroceryAssistant with Excel database")
        self.categories_list = []
        self.category_map = {}
        self.products_df = None
        self.categories_df = None
        self.llm = None
        self._load_excel_data()
        self._init_llm()
        logger.info("GroceryAssistant initialized successfully with Excel data")

    def _load_excel_data(self):
        """Load categories and products from Excel file"""
        try:
            logger.info("Loading data from Excel file: Buy2Cash_SampleDB.xlsx")
            
            # Load categories sheet with exact field names: _id, name
            self.categories_df = pd.read_excel("asset\\Buy2Cash_SampleDB.xlsx", sheet_name="categories")
            logger.info(f"Loaded {len(self.categories_df)} categories from Excel")
            logger.debug(f"Categories columns: {list(self.categories_df.columns)}")
            
            # Load products sheet with exact field names
            self.products_df = pd.read_excel("asset\\Buy2Cash_SampleDB.xlsx", sheet_name="Products")
            logger.info(f"Loaded {len(self.products_df)} products from Excel")
            logger.debug(f"Products columns: {list(self.products_df.columns)}")
            self.categories_list = []
            for _, row in self.categories_df.iterrows():
                category_id = row["_id"]
                category_name = str(row["name"]).strip() if pd.notna(row["name"]) else "Unknown"
                
                normalized_cat = {
                    "_id": normalize_mongo_id(category_id),
                    "name": category_name
                }
                self.categories_list.append(normalized_cat)
            self.category_map = {}
            for cat in self.categories_list:
                cat_name = str(cat["name"]) if cat["name"] is not None else ""
                if cat_name:  
                    name_variations = [
                        cat_name.lower(),
                        cat_name.lower().strip(),
                        cat_name.replace(" ", "").lower(),
                        cat_name.replace("&", "and").lower()
                    ]
                    for variation in name_variations:
                        if variation:  
                            self.category_map[variation] = cat
            
            logger.info(f"Successfully processed {len(self.categories_list)} categories")
            
        except Exception as e:
            logger.error(f"Error loading Excel data: {e}")
            logger.error(f"Error details: {type(e).__name__}: {str(e)}")
            raise ValueError(f"Failed to load Excel data: {e}")

    def get_category_by_id(self, category_id):
        """Fetch category by ID from categories DataFrame"""
        try:
            category_row = self.categories_df[self.categories_df['_id'] == category_id]
            if category_row.empty:
                category_row = self.categories_df[self.categories_df['_id'].astype(str) == str(category_id)]
            
            if not category_row.empty:
                return category_row.iloc[0].to_dict()
            else:
                logger.warning(f"Category with ID {category_id} not found")
                return None
        except Exception as e:
            logger.error(f"Error fetching category by ID {category_id}: {e}")
            return None

    def _init_llm(self):
        """Initialize OpenAI LLM"""
        try:
            logger.info("Initializing OpenAI LLM")
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found")
            
            self.llm = ChatOpenAI(
                model="gpt-4o-mini", 
                openai_api_key=api_key, 
                temperature=0.2
            )
            logger.info("OpenAI LLM initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing LLM: {e}")
            raise ValueError(f"Failed to initialize LLM: {e}")

    def _extract_json_from_response(self, response_content: str):
        """Extract and validate JSON from LLM response"""
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
            json_match = re.search(json_pattern, cleaned_content, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(0)
                return json.loads(json_str)
            else:
                return json.loads(cleaned_content)
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            logger.error(f"Cleaned content: {cleaned_content}")
            raise
        except Exception as e:
            logger.error(f"Error extracting JSON: {e}")
            raise

    def generate_ingredients(self, user_query: str):
        """Extract categories and ingredients from user query using Excel data"""
        logger.info(f"Generating ingredients for query: '{user_query[:50]}...'")
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                category_list = "\n".join([f'- {cat["name"]}' for cat in self.categories_list])
                
                prompt = f'''You are a culinary-aware grocery assistant with expertise in cuisine compatibility and cooking practices.

Analyze this cooking request and respond with ONLY valid JSON containing ingredients that are actually suitable for the dish/cuisine mentioned.

User request: "{user_query}"

Available Categories:
{category_list}

IMPORTANT GUIDELINES:
1. Match ingredients to the specific cuisine/dish mentioned (e.g., Italian for pizza, Indian for curry)
2. Avoid suggesting ingredients from incompatible cuisines unless fusion cooking is explicitly mentioned
3. Focus on ingredients that are commonly and traditionally used for the requested dish
4. Consider real-world cooking practices and flavor compatibility

Examples:
- For "pizza": suggest cheese, pizza sauce, Italian herbs, NOT Indian masalas
- For "curry": suggest Indian spices, NOT pizza sauce
- For "pasta": suggest Italian ingredients, NOT South Indian spice powders

Response format (JSON only):
{{
  "categories": [
    {{
      "category": "<exact category name from list>",
      "items": ["item1", "item2"]
    }}
  ]
}}

Respond with ONLY the JSON structure above:'''
                
                response = self.llm.invoke(prompt)
                result = self._extract_json_from_response(response.content)

                if not isinstance(result, dict) or "categories" not in result:
                    raise ValueError("Invalid response structure")
                
                normalized_categories = []
                for cat_entry in result.get("categories", []):
                    category_name = cat_entry.get("category", "").strip()
                    items = cat_entry.get("items", [])
                    canonical_category = self._find_category(category_name)
                    normalized_categories.append({
                        "category": {
                            "_id": canonical_category["_id"],
                            "name": canonical_category["name"]
                        },
                        "items": items
                    })
                
                logger.info(f"Successfully generated {len(normalized_categories)} categories with IDs")
                
                return {
                    "query": user_query,
                    "timestamp": datetime.now().isoformat(),
                    "categories": normalized_categories
                }
                
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Attempt {attempt + 1} failed with JSON error: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"All attempts failed for generate_ingredients")
                    raise HTTPException(status_code=500, detail="Failed to generate valid response")
                continue
            except Exception as e:
                logger.error(f"Error in generate_ingredients: {e}")
                raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

    def _find_category(self, category_name: str):
        """Find category by name with improved matching"""
        safe_category_name = str(category_name) if category_name is not None else ""
        
        if not safe_category_name.strip():
            logger.warning(f"Empty category name provided")
            return {
                "_id": {"$oid": "UNKNOWN"},
                "name": "Unknown"
            }
        
        name_variations = [
            safe_category_name.lower().strip(),
            safe_category_name.replace(" ", "").lower(),
            safe_category_name.replace("&", "and").lower(),
            safe_category_name.replace("and", "&").lower()
        ]
        
        for name_key in name_variations:
            if name_key:  
                found_category = self.category_map.get(name_key)
                if found_category:
                    return found_category
        
        logger.warning(f"Unknown category: {safe_category_name}")
        return {
            "_id": {"$oid": "UNKNOWN"},
            "name": safe_category_name
        }

    def validate_product_suitability(self, user_query: str, typical_use: str):
        """Enhanced LLM validator with better context"""
        try:
            safe_query = str(user_query) if user_query is not None else ""
            safe_typical_use = str(typical_use) if typical_use is not None else ""
            
            if not safe_query.strip() or not safe_typical_use.strip():
                logger.warning("Empty query or typical_use provided to validator")
                return False
            
            prompt = f'''You are a culinary expert. Analyze if this product is suitable for the user's cooking request.

User Query: "{safe_query}"
Product Typical Use: "{safe_typical_use}"

Consider:
1. Cuisine compatibility (Italian pizza vs Indian spices)
2. Traditional cooking methods
3. Flavor profiles that work together
4. Real-world cooking practices

Examples:
- Cheese is perfect for pizza
- Marinara sauce works for pizza
- Indian chicken masala powder is NOT suitable for traditional pizza
- Idly chili powder is NOT suitable for pizza (completely different cuisine)

Respond with ONLY: YES or NO'''
            
            response = self.llm.invoke(prompt)
            result = response.content.strip().upper()
            return result.startswith("YES")
            
        except Exception as e:
            logger.error(f"Error in product suitability validation: {e}")
            return False

    def infer_metadata(self, user_query: str):
        """Generate metadata using LLM with enhanced prompts"""
        logger.info(f"Inferring metadata for query: '{user_query[:50]}...'")
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                prompt = f'''Analyze this grocery shopping query and extract food metadata.

Query: "{user_query}"

Identify the dish being prepared, cuisine type, dietary preference, and meal timing.

Response format (JSON only):
{{
  "dishbased": ["dish_name"],
  "cuisinebased": ["cuisine_type"],
  "dietarypreferences": ["Vegan", "Vegetarian", "Gluten-Free", "Dairy-Free"],
  "timebased": ["based on timestamp and the dish decide the time based"]
}}

Example:
Query: "I want to make breakfast"
Response: {{"dishbased": ["breakfast"], "cuisinebased": ["american"], "dietarypreferences": ["vegetarian"], "timebased": ["breakfast"]}}

Try to fill all fields based on the query. If unsure, use general terms.
Respond with ONLY the JSON structure above:'''
                
                response = self.llm.invoke(prompt)
                result = self._extract_json_from_response(response.content)
                
                metadata = {
                    "dishbased": result.get("dishbased", []),
                    "cuisinebased": result.get("cuisinebased", []),
                    "dietarypreferences": result.get("dietarypreferences", []),
                    "timebased": result.get("timebased", [])
                }
                
                total_items = sum(len(v) for v in metadata.values())
                if total_items == 0:
                    metadata = {
                        "dishbased": ["general"],
                        "cuisinebased": ["international"],
                        "dietarypreferences": ["mixed"],
                        "timebased": ["general"]
                    }
                
                logger.info(f"Successfully inferred metadata: {metadata}")
                return metadata
                
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Metadata attempt {attempt + 1} failed with JSON error: {e}")
                if attempt == max_retries - 1:
                    logger.warning("All metadata attempts failed, using fallback")
                    return {
                        "dishbased": ["general"],
                        "cuisinebased": ["international"],
                        "dietarypreferences": ["mixed"],
                        "timebased": ["general"]
                    }
                continue
            except Exception as e:
                logger.error(f"Error in metadata inference: {e}")
                return {
                    "dishbased": ["general"],
                    "cuisinebased": ["international"],
                    "dietarypreferences": ["mixed"],
                    "timebased": ["general"]
                }

# Global assistant instance
assistant = GroceryAssistant()
