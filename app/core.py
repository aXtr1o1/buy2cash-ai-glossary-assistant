import json
import os
import logging
import re
from datetime import datetime
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from fastapi import HTTPException
from app.utils import normalize_mongo_id

logger = logging.getLogger(__name__)
load_dotenv(dotenv_path="config.env")

class GroceryAssistant:
    def __init__(self):
        logger.info("Initializing GroceryAssistant")
        self.categories_list = []
        self.category_map = {}
        self.llm = None
        self._load_categories()
        self._init_llm()
        logger.info("GroceryAssistant initialized successfully")

    def _load_categories(self):
        """Load categories from JSON file"""
        try:
            logger.info("Loading categories from JSON file")
            with open("asset/categories.json", "r", encoding='utf-8') as f:
                raw_categories = json.load(f)
            
            self.categories_list = []
            for cat in raw_categories:
                normalized_cat = {
                    "_id": normalize_mongo_id(cat["_id"]),
                    "name": cat["name"]
                }
                self.categories_list.append(normalized_cat)
            
            self.category_map = {}
            for cat in self.categories_list:
                name_variations = [
                    cat["name"].lower(),
                    cat["name"].lower().strip(),
                    cat["name"].replace(" ", "").lower(),
                    cat["name"].replace("&", "and").lower()
                ]
                for variation in name_variations:
                    self.category_map[variation] = cat
            
            logger.info(f"Successfully loaded {len(self.categories_list)} categories")
            
        except Exception as e:
            logger.error(f"Error loading categories: {e}")
            raise ValueError(f"Failed to load categories: {e}")

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
            # Remove any markdown formatting
            cleaned_content = response_content.strip()
            if cleaned_content.startswith('```'):
                cleaned_content = cleaned_content[7:]
            if cleaned_content.endswith('```'):
                cleaned_content = cleaned_content[:-3]
            
            # Remove any extra whitespace or newlines
            cleaned_content = cleaned_content.strip()
            
            # Try to find JSON content using regex
            json_pattern = r'\{.*\}'
            json_match = re.search(json_pattern, cleaned_content, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(0)
                return json.loads(json_str)
            else:
                # If no JSON pattern found, try parsing the whole content
                return json.loads(cleaned_content)
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            logger.error(f"Cleaned content: {cleaned_content}")
            raise
        except Exception as e:
            logger.error(f"Error extracting JSON: {e}")
            raise

    def generate_ingredients(self, user_query: str):
        """Extract categories and ingredients from user query"""
        logger.info(f"Generating ingredients for query: '{user_query[:50]}...'")
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                category_list = "\n".join([f'- {cat["name"]}' for cat in self.categories_list])
                
                prompt = f'''You are a grocery assistant. Analyze this request and respond with ONLY valid JSON.

User request: "{user_query}"

Available Categories:
{category_list}

Response format (JSON only):
{{
  "categories": [
    {{
      "category": "<exact category name from list>",
      "items": ["item1", "item2"]
    }}
  ]
}}

Example:
User: "I need ingredients for pasta"
Response: {{"categories": [{{"category": "Masalas", "items": ["salt", "pepper", "herbs"]}}]}}

Respond with ONLY the JSON structure above:'''
                
                response = self.llm.invoke(prompt)
                result = self._extract_json_from_response(response.content)
                
                # Validate the structure
                if not isinstance(result, dict) or "categories" not in result:
                    raise ValueError("Invalid response structure")
                
                normalized_categories = []
                for cat_entry in result.get("categories", []):
                    category_name = cat_entry.get("category", "").strip()
                    items = cat_entry.get("items", [])
                    canonical_category = self._find_category(category_name)
                    normalized_categories.append({
                        "category": canonical_category,
                        "items": items
                    })
                
                logger.info(f"Successfully generated {len(normalized_categories)} categories")
                
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
        name_variations = [
            category_name.lower().strip(),
            category_name.replace(" ", "").lower(),
            category_name.replace("&", "and").lower(),
            category_name.replace("and", "&").lower()
        ]
        
        for name_key in name_variations:
            found_category = self.category_map.get(name_key)
            if found_category:
                return found_category
        
        logger.warning(f"Unknown category: {category_name}")
        return {
            "_id": {"$oid": "UNKNOWN"},
            "name": category_name
        }

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
  "dietarypreferences": ["diet_type"],
  "timebased": ["based on timestamp and the dish decide the time based"]
}}

Example:
Query: "I want to make breakfast"
Response: {{"dishbased": ["breakfast"], "cuisinebased": ["american"], "dietarypreferences": ["vegetarian"], "timebased": ["breakfast"]}}

Respond with ONLY the JSON structure above:'''
                
                response = self.llm.invoke(prompt)
                result = self._extract_json_from_response(response.content)
                
                # Validate and ensure all fields exist
                metadata = {
                    "dishbased": result.get("dishbased", []),
                    "cuisinebased": result.get("cuisinebased", []),
                    "dietarypreferences": result.get("dietarypreferences", []),
                    "timebased": result.get("timebased", [])
                }
                
                # Ensure at least some fields are populated
                total_items = sum(len(v) for v in metadata.values())
                if total_items == 0:
                    # Provide minimal fallback
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
