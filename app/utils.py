import logging

logger = logging.getLogger(__name__)

def get_oid(val):
    """Extract ObjectId string from MongoDB _id field with enhanced handling"""
    try:
        if val is None:
            logger.warning("get_oid received None value")
            return "None"
        elif isinstance(val, dict) and "$oid" in val:
            oid_value = val["$oid"]
            logger.debug(f"Extracted OID from dict: {oid_value}")
            return str(oid_value)
        elif isinstance(val, str):
            logger.debug(f"Using string as OID: {val}")
            return val
        else:
            logger.warning(f"Converting unknown type to OID: {type(val)} = {val}")
            return str(val)
    except Exception as e:
        logger.error(f"Error extracting OID from {val}: {e}")
        return str(val) if val is not None else "None"

def normalize_mongo_id(val):
    """Convert to canonical MongoDB format: {"$oid": "..."}"""
    try:
        if val is None:
            logger.warning("normalize_mongo_id received None value")
            return {"$oid": "None"}
        elif isinstance(val, dict) and "$oid" in val:
            return val
        elif isinstance(val, str):
            return {"$oid": val}
        else:
            return {"$oid": str(val) if val is not None else "None"}
    except Exception as e:
        logger.error(f"Error normalizing mongo ID {val}: {e}")
        return {"$oid": str(val) if val is not None else "None"}

def safe_float(val, fallback=0.0):
    """Safely convert value to float"""
    try:
        return float(val) if val is not None else fallback
    except (ValueError, TypeError):
        return fallback

logger.info("Utils module loaded successfully")
