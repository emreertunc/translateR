"""
Utility Functions

Common helper functions used throughout the application.
"""

from typing import Dict, List, Optional


# App Store supported locales with their language names
APP_STORE_LOCALES = {
    "ar": "Arabic",
    "ca": "Catalan", 
    "zh-Hans": "Chinese (Simplified)",
    "zh-Hant": "Chinese (Traditional)",
    "hr": "Croatian",
    "cs": "Czech",
    "da": "Danish",
    "nl-NL": "Dutch",
    "en-AU": "English (Australia)",
    "en-CA": "English (Canada)", 
    "en-GB": "English (U.K.)",
    "en-US": "English (U.S.)",
    "fi": "Finnish",
    "fr-FR": "French",
    "fr-CA": "French (Canada)",
    "de-DE": "German",
    "el": "Greek",
    "he": "Hebrew",
    "hi": "Hindi",
    "hu": "Hungarian",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "ms": "Malay",
    "no": "Norwegian",
    "pl": "Polish",
    "pt-BR": "Portuguese (Brazil)",
    "pt-PT": "Portuguese (Portugal)",
    "ro": "Romanian",
    "ru": "Russian",
    "sk": "Slovak",
    "es-MX": "Spanish (Mexico)",
    "es-ES": "Spanish (Spain)",
    "sv": "Swedish",
    "th": "Thai",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "vi": "Vietnamese"
}

# Character limits for App Store fields
FIELD_LIMITS = {
    "name": 30,
    "subtitle": 30,
    "description": 4000,
    "keywords": 100,
    "promotional_text": 170,
    "whats_new": 4000,
    "privacy_policy_url": 255,
    "marketing_url": 255,
    "support_url": 255
}


def truncate_keywords(keywords: str, max_length: int = 100) -> str:
    """
    Truncate keywords to fit within character limit while preserving complete keywords.
    
    Args:
        keywords: Comma-separated keywords string
        max_length: Maximum character length allowed
        
    Returns:
        Truncated keywords string
    """
    if not keywords or len(keywords) <= max_length:
        return keywords
    
    keyword_list = [k.strip() for k in keywords.split(',')]
    truncated_keywords = []
    current_length = 0
    
    for keyword in keyword_list:
        # Calculate length including comma separator
        new_length = current_length + len(keyword) + (2 if truncated_keywords else 0)
        
        if new_length <= max_length:
            truncated_keywords.append(keyword)
            current_length = new_length
        else:
            break
    
    return ', '.join(truncated_keywords)


def validate_field_length(text: str, field_name: str) -> bool:
    """
    Validate that text doesn't exceed field character limit.
    
    Args:
        text: Text to validate
        field_name: Name of the field being validated
        
    Returns:
        True if text is within limit, False otherwise
    """
    limit = FIELD_LIMITS.get(field_name)
    if limit is None:
        return True
    
    return len(text) <= limit


def get_field_limit(field_name: str) -> Optional[int]:
    """
    Get character limit for a specific field.
    
    Args:
        field_name: Name of the field
        
    Returns:
        Character limit or None if no limit defined
    """
    return FIELD_LIMITS.get(field_name)


def detect_base_language(localizations: List[Dict]) -> Optional[str]:
    """
    Detect base language from existing localizations.
    Prefers English variants, then uses first available.
    
    Args:
        localizations: List of localization data from API
        
    Returns:
        Base language locale code or None
    """
    if not localizations:
        return None
    
    # Preferred base languages in order
    preferred_locales = ["en-US", "en-GB", "en-CA", "en-AU"]
    
    # Extract locale codes from localizations
    available_locales = [loc.get("attributes", {}).get("locale") for loc in localizations]
    available_locales = [loc for loc in available_locales if loc]
    
    # Try preferred locales first
    for locale in preferred_locales:
        if locale in available_locales:
            return locale
    
    # Return first available locale
    return available_locales[0] if available_locales else None


def format_progress(current: int, total: int, operation: str = "") -> str:
    """
    Format progress message for display.
    
    Args:
        current: Current progress count
        total: Total count
        operation: Description of current operation
        
    Returns:
        Formatted progress string
    """
    percentage = int((current / total) * 100) if total > 0 else 0
    bar_length = 20
    filled_length = int(bar_length * current // total) if total > 0 else 0
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    
    return f"[{bar}] {percentage}% ({current}/{total}) {operation}"


def print_success(message: str):
    """Print success message with formatting."""
    print(f"✅ {message}")


def print_error(message: str):
    """Print error message with formatting."""
    print(f"❌ {message}")


def print_warning(message: str):
    """Print warning message with formatting."""
    print(f"⚠️  {message}")


def print_info(message: str):
    """Print info message with formatting."""
    print(f"ℹ️  {message}")