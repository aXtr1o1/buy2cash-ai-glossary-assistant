import logging

logger = logging.getLogger(__name__)

def safe_float(val, fallback=0.0):
    """Safely convert value to float"""
    try:
        if val is None:
            return fallback
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            cleaned = val.strip().replace(',', '').replace('$', '')
            return float(cleaned) if cleaned else fallback
        return fallback
    except (ValueError, TypeError):
        return fallback

def safe_int(val, fallback=0):
    """Safely convert value to int"""
    try:
        if val is None:
            return fallback
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            return int(val)
        if isinstance(val, str):
            cleaned = val.strip().replace(',', '')
            return int(float(cleaned)) if cleaned else fallback
        return fallback
    except (ValueError, TypeError):
        return fallback

def normalize_text(text):
    """Normalize text for better matching"""
    if not text or not isinstance(text, str):
        return ""
    normalized = text.lower().strip()
    normalized = ' '.join(normalized.split())
    
    return normalized

def calculate_match_confidence(score, method="fuzzy"):
    """Calculate confidence level based on match score"""
    if method == "exact":
        return "HIGH" if score == 100 else "MEDIUM"
    elif method == "word":
        if score >= 90:
            return "HIGH"
        elif score >= 75:
            return "MEDIUM"
        else:
            return "LOW"
    else:  
        if score >= 85:
            return "HIGH"
        elif score >= 70:
            return "MEDIUM"
        elif score >= 60:
            return "LOW"
        else:
            return "VERY_LOW"

logger.info("Enhanced utils module loaded successfully")
