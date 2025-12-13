"""
Utility Functions

Common helper functions used throughout the application.
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path


# App Store supported locales with their language names
APP_STORE_LOCALES = {
    "ar-SA": "Arabic",
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
    "support_url": 255,
    "iap_name": 30,
    "iap_description": 45,
    "subscription_name": 60,
    "subscription_description": 200,
    "subscription_group_name": 60,
    "subscription_group_custom_app_name": 30,
    # In-app events (App Store in-app events)
    "app_event_name": 30,
    "app_event_short_description": 50,
    "app_event_long_description": 120,
}


def truncate_keywords(keywords: str, max_length: int = 100) -> str:
    """
    Truncate keywords to fit within character limit while preserving complete keywords.
    
    Args:
        keywords: Comma-separated keywords string
        max_length: Maximum character length allowed
        
    Returns:
        Truncated keywords string (ASO optimized format: word1,word2,word3)
    """
    if not keywords:
        return keywords
        
    # Clean input: remove trailing periods, extra spaces
    keywords = keywords.strip().rstrip('.')
    
    if len(keywords) <= max_length:
        # Still format properly even if under limit
        keyword_list = [k.strip() for k in keywords.split(',')]
        return ','.join(keyword_list)
    
    keyword_list = [k.strip() for k in keywords.split(',')]
    truncated_keywords = []
    current_length = 0
    
    for keyword in keyword_list:
        # Skip empty keywords
        if not keyword:
            continue
            
        # Calculate length including comma separator (no space for ASO optimization)
        new_length = current_length + len(keyword) + (1 if truncated_keywords else 0)
        
        if new_length <= max_length:
            truncated_keywords.append(keyword)
            current_length = new_length
        else:
            break
    
    return ','.join(truncated_keywords)


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


# --------------------------
# Translation helpers (shared)
# --------------------------

def provider_model_info(provider: Any, fallback_name: Optional[str] = None) -> (str, Optional[str]):
    """Return display-friendly provider name and model string."""
    try:
        name = provider.get_name()  # type: ignore[attr-defined]
    except Exception:
        name = fallback_name or str(provider)
    model = getattr(provider, "model", None)
    return name, model


def show_provider_and_source(
    provider: Any,
    provider_key: Optional[str],
    base_locale: str,
    source_text: str,
    title: str = "Source text to translate",
    seed: Optional[int] = None,
    **kwargs,
) -> None:
    """Print provider/model info and a source text preview with language.

    Accepts optional seed for display; extra kwargs are ignored for forward compatibility.
    """
    name, model = provider_model_info(provider, provider_key)
    if seed is not None:
        print_info(f"AI provider: {name} — model: {model or 'n/a'} — seed: {seed}")
    else:
        print_info(f"AI provider: {name} — model: {model or 'n/a'}")
    print_info(title + ":")
    print("-" * 60)
    print(f"Language: {APP_STORE_LOCALES.get(base_locale, base_locale)} [{base_locale}]")
    print("-" * 60)
    try:
        sys.stdout.write(source_text + "\n\n")
        sys.stdout.flush()
    except Exception:
        print(source_text)


def parallel_map_locales(
    target_locales: List[str],
    task_fn,
    progress_action: str = "Translated",
    concurrency_env_var: str = "TRANSLATER_CONCURRENCY",
    default_workers: Optional[int] = None,
    pacing_seconds: float = 0.0,
):
    """Run per-locale tasks in parallel with progress and error reporting.

    Args:
        target_locales: List of locale codes to process.
        task_fn: Callable(loc: str) -> Any. May raise to signal error.
        progress_action: Verb displayed in progress line (e.g., "Translated").
        concurrency_env_var: Env var name to override concurrency.
        default_workers: Default max workers if env not set.
        pacing_seconds: Optional sleep per task after completion (to ease rate limits).

    Returns:
        (results_by_locale, errors_by_locale)
    """
    total = len(target_locales)
    results: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    if total == 0:
        return results, errors

    # Wrap the task to apply pacing
    def _runner(loc: str):
        try:
            val = task_fn(loc)
            return (loc, val, None)
        except Exception as e:  # noqa: BLE001
            return (loc, None, str(e))
        finally:
            if pacing_seconds and pacing_seconds > 0:
                try:
                    time.sleep(pacing_seconds)
                except Exception:
                    pass

    # Resolve concurrency
    # Determine default worker count: CPU count if not provided
    cpu_default = os.cpu_count() or 4
    base_default = default_workers if isinstance(default_workers, int) and default_workers > 0 else cpu_default
    try:
        env_val = os.environ.get(concurrency_env_var, str(base_default)) or str(base_default)
        max_workers = max(1, min(total, int(env_val)))
    except Exception:
        max_workers = min(total, base_default)

    completed = 0
    # Show initial 0/x progress so users see activity immediately
    last_len = 0
    try:
        line = format_progress(0, total, f"{progress_action}...")
        sys.stdout.write("\r" + line)
        sys.stdout.flush()
        last_len = len(line)
    except Exception:
        try:
            print(format_progress(0, total, f"{progress_action}..."))
        except Exception:
            pass
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_map = {ex.submit(_runner, loc): loc for loc in target_locales}
        for fut in as_completed(future_map):
            loc = future_map[fut]
            language = APP_STORE_LOCALES.get(loc, loc)
            try:
                _loc, val, err = fut.result()
            except Exception as e:  # shouldn't happen with wrapper, but safety
                val, err = None, str(e)
            if err:
                print_error(f"  ❌ {progress_action} {language} failed: {err}")
                errors[loc] = err
            else:
                results[loc] = val
            completed += 1
            # Progress update
            try:
                line = format_progress(completed, total, f"{progress_action} {language}")
                pad = max(0, last_len - len(line))
                sys.stdout.write("\r" + line + (" " * pad))
                sys.stdout.flush()
                last_len = len(line)
            except Exception:
                print(format_progress(completed, total, f"{progress_action} {language}"))
    # Clear progress line
    try:
        sys.stdout.write("\r" + (" " * last_len) + "\r")
        sys.stdout.flush()
    except Exception:
        pass
    print()
    return results, errors


# --------------------------
# Prompt refinement helpers
# --------------------------

REFINE_HEADER = "# Prompt Refinement: add notes below to guide the translation"
REFINE_PROMPT_PREFIX = "# PROMPT:"


def build_refinement_template(default_refinement: str, body: str) -> str:
    """Build a pre-filled multiline template including refinement comments and body.

    Comments are ignored when sending text for translation; users can edit the
    PROMPT line and/or add additional comment lines starting with '#'.
    """
    lines = [
        REFINE_HEADER,
        f"{REFINE_PROMPT_PREFIX} {default_refinement}".rstrip(),
        "",
    ]
    if body:
        lines.append(body)
    return "\n".join(lines)


def parse_refinement_template(text: str, fallback_default: str = "") -> (str, str):
    """Parse an edited template into (clean_text, refinement_phrase).

    - Collects the '# PROMPT:' line value if present (else uses fallback_default)
    - Concatenates any additional comment lines (starting with '#') as extra guidance
    - Returns the non-comment body as the translation text (stripped)
    """
    if text is None:
        return "", (fallback_default or "")
    refinement_from_prompt = None
    extra_guidance: List[str] = []
    body_lines: List[str] = []
    in_header = True
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if stripped.startswith("#") and in_header:
            # Comment header section
            if stripped.upper().startswith(REFINE_PROMPT_PREFIX):
                # After ':' is the default refinement; keep exact text after prefix
                idx = line.find(":")
                val = line[idx + 1:].strip() if idx != -1 else ""
                refinement_from_prompt = val
            elif stripped == REFINE_HEADER:
                # Skip header marker
                pass
            else:
                # Treat any other header comment lines as extra guidance
                extra = line.lstrip("#").strip()
                if extra:
                    extra_guidance.append(extra)
            continue
        else:
            in_header = False
            body_lines.append(raw)
    clean_text = "\n".join(body_lines).strip()
    base_refine = refinement_from_prompt if (refinement_from_prompt is not None) else (fallback_default or "")
    if extra_guidance:
        if base_refine:
            combined = base_refine + " \n" + " \n".join(extra_guidance)
        else:
            combined = " \n".join(extra_guidance)
    else:
        combined = base_refine
    return clean_text, combined.strip()


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


# Default directory for App Store Connect private keys (p8)
DEFAULT_APPSTORE_P8_DIR = Path.home() / ".appstoreconnect" / "private_keys"


def resolve_private_key_path(key_id: str, configured_path: Optional[str] = None) -> Path:
    """
    Resolve the App Store Connect private key (.p8) file path.

    Resolution order:
    1) If configured_path is provided and exists (after expanding ~), use it.
    2) If configured_path is provided but not found:
       - If it's a bare filename, try in DEFAULT_APPSTORE_P8_DIR.
    3) Fallback to DEFAULT_APPSTORE_P8_DIR / f"AuthKey_{key_id}.p8" if exists.

    Args:
        key_id: App Store Connect API Key ID (used for default filename)
        configured_path: Optional path or filename provided via config

    Returns:
        Path to the resolved private key file

    Raises:
        FileNotFoundError: If no suitable key file is found
    """
    # 1) Respect explicit configured path if it exists
    if configured_path:
        # Expand user and make absolute
        p = Path(os.path.expanduser(configured_path))
        if p.exists():
            return p

        # 2) If just a filename, try in default dir
        if p.name and (not p.parent or str(p).find(os.sep) == -1):
            candidate = DEFAULT_APPSTORE_P8_DIR / p.name
            if candidate.exists():
                return candidate

    # 3) Try the conventional filename in the default directory
    conventional = DEFAULT_APPSTORE_P8_DIR / f"AuthKey_{key_id}.p8"
    if conventional.exists():
        return conventional

    # Nothing found
    raise FileNotFoundError(
        f"Could not locate .p8 key. Tried configured path '{configured_path}' and '{conventional}'."
    )
