"""
Utility Functions

Common helper functions used throughout the application.
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Any


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


def export_existing_localizations(localizations_data: List[Dict[str, Any]], app_name: str = "Unknown App", app_id: str = "unknown", version_string: str = "unknown") -> str:
    """
    Export existing localizations to a timestamped file.
    
    Args:
        localizations_data: List of localization data from App Store Connect API
        app_name: Name of the app for the export file
        app_id: App ID for the export file
        version_string: App version string for the export file
        
    Returns:
        Path to the created export file
    """
    timestamp = datetime.now().strftime("%d%m%Y_%H.%M")
    
    # Clean app name for filename (remove spaces, special characters)
    clean_app_name = "".join(c.lower() for c in app_name if c.isalnum() or c in "-_")[:20]
    if not clean_app_name:
        clean_app_name = "unknown_app"
    
    # Clean version string for filename
    clean_version = "".join(c for c in version_string if c.isalnum() or c in ".-_")
    if not clean_version or clean_version == "unknown":
        clean_version = "v_unknown"
    elif not clean_version.startswith('v'):
        clean_version = f"v{clean_version}"
    
    os.makedirs("existing_localizations", exist_ok=True)
    filename = f"existing_localizations/{clean_app_name}_{app_id}_{clean_version}_{timestamp}.txt"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"=== EXISTING LOCALIZATIONS EXPORT ===\n")
        f.write(f"App: {app_name}\n")
        f.write(f"App ID: {app_id}\n")
        f.write(f"Version: {version_string}\n")
        f.write(f"Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total Languages: {len(localizations_data)}\n")
        f.write("=" * 50 + "\n\n")
        
        for localization in localizations_data:
            attributes = localization.get("attributes", {})
            locale = attributes.get("locale", "Unknown")
            language_name = APP_STORE_LOCALES.get(locale, "Unknown Language")
            
            f.write(f"{language_name} ({locale}):\n")
            f.write("-" * 30 + "\n")
            
            name = attributes.get("name")
            if name:
                f.write(f"Name: {name}\n")
            
            subtitle = attributes.get("subtitle") 
            if subtitle:
                f.write(f"Subtitle: {subtitle}\n")
            
            description = attributes.get("description")
            if description:
                f.write(f"Description: {description}\n")
            
            keywords = attributes.get("keywords")
            if keywords:
                f.write(f"Keywords: {keywords}\n")
            
            promotional_text = attributes.get("promotionalText")
            if promotional_text:
                f.write(f"Promotional Text: {promotional_text}\n")
            
            whats_new = attributes.get("whatsNew")
            if whats_new:
                f.write(f"What's New: {whats_new}\n")
            
            f.write("\n")
    
    return filename