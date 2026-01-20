"""
Configuration Management

Handles loading and saving of configuration files including API keys,
provider settings, and user preferences.
"""

import copy
import json
import os
from typing import Dict, Any, Optional
from pathlib import Path

DEFAULT_PROVIDERS_TEMPLATE: Dict[str, Any] = {
    "default_provider": "",  # optional: when set, used as default in workflows
    "prompt_refinement": "",  # optional: phrase appended to translation prompts
    "anthropic": {
        "name": "Anthropic Claude",
        "class": "AnthropicProvider",
        "models": [
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250514",
            "claude-3-7-sonnet-20250219",
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229"
        ],
        "default_model": "claude-sonnet-4-20250514"
    },
    "openai": {
        "name": "OpenAI GPT",
        "class": "OpenAIProvider",
        "models": [
            "gpt-5.2",
            "gpt-5.1",
            "gpt-5-mini",
            "gpt-5-nano",
            "gpt-5-chat-latest",
            "gpt-5-2025-08-07",
            "gpt-5-mini-2025-08-07",
            "gpt-5-nano-2025-08-07",
            "gpt-4.1",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo"
        ],
        "default_model": "gpt-5.2"
    },
    "google": {
        "name": "Google Gemini",
        "class": "GoogleGeminiProvider",
        "models": [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite"
        ],
        "default_model": "gemini-2.5-flash"
    }
}


class ConfigManager:
    """Manages application configuration and API keys."""
    
    def __init__(self, config_dir: str = "config"):
        """
        Initialize configuration manager.
        
        Args:
            config_dir: Directory containing configuration files
        """
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        
        self.providers_file = self.config_dir / "providers.json"
        self.api_keys_file = self.config_dir / "api_keys.json"
        self.instructions_file = self.config_dir / "instructions.txt"
        
        self._ensure_config_files()
    
    def _ensure_config_files(self):
        """Create default configuration files if they don't exist."""
        if not self.providers_file.exists():
            self._create_default_providers()
        else:
            self._sync_provider_catalog()
        
        if not self.api_keys_file.exists():
            self._create_default_api_keys()
        
        if not self.instructions_file.exists():
            self._create_default_instructions()
    
    def _create_default_providers(self):
        """Create default providers configuration."""
        with open(self.providers_file, "w") as f:
            json.dump(copy.deepcopy(DEFAULT_PROVIDERS_TEMPLATE), f, indent=2)
    
    def _sync_provider_catalog(self):
        """
        Keep providers.json in sync with the baked-in model lists so new models
        are picked up automatically without manual edits.
        """
        try:
            cfg = self.load_providers()
        except Exception:
            return
        
        changed = False
        # Ensure global keys exist
        for meta_key in ("default_provider", "prompt_refinement"):
            if meta_key not in cfg:
                cfg[meta_key] = DEFAULT_PROVIDERS_TEMPLATE.get(meta_key, "")
                changed = True
        
        for provider_name, defaults in DEFAULT_PROVIDERS_TEMPLATE.items():
            if provider_name in ("default_provider", "prompt_refinement"):
                continue
            existing = cfg.get(provider_name)
            if not isinstance(existing, dict):
                cfg[provider_name] = copy.deepcopy(defaults)
                changed = True
                continue
            
            # Update static metadata and model list from the template
            for key in ("name", "class", "models"):
                if existing.get(key) != defaults.get(key):
                    existing[key] = copy.deepcopy(defaults.get(key))
                    changed = True
            
            models = existing.get("models") or []
            default_model = existing.get("default_model")
            if default_model not in models:
                fallback = defaults.get("default_model")
                if fallback not in models and models:
                    fallback = models[0]
                if fallback:
                    existing["default_model"] = fallback
                    changed = True
            
            cfg[provider_name] = existing
        
        if changed:
            try:
                self.save_providers(cfg)
            except Exception:
                # If saving fails (e.g., read-only), still allow runtime to use the updated dict
                pass
    
    def _create_default_api_keys(self):
        """Create default API keys template."""
        default_keys = {
            "app_store_connect": {
                "key_id": "",
                "issuer_id": "",
                "private_key_path": ""
            },
            "ai_providers": {
                "anthropic": "",
                "openai": "",
                "google": ""
            }
        }
        
        with open(self.api_keys_file, "w") as f:
            json.dump(default_keys, f, indent=2)
    
    def _create_default_instructions(self):
        """Create default translation instructions."""
        instructions = """You are a professional translator specializing in App Store metadata translation.

CRITICAL REQUIREMENTS:
1. Character Limits: ABSOLUTELY NEVER exceed the specified character limit for any field
   - CHARACTER LIMITS INCLUDE ALL SPACES, PUNCTUATION, AND SPECIAL CHARACTERS
   - Count every single character including spaces between words
   - If needed, make translations slightly more concise while preserving meaning
   - Use shorter synonyms or rephrase sentences when character limit is approached
   - MEANING AND CONTEXT MUST NEVER BE COMPROMISED - only make minor adjustments for length
2. Marketing Tone: Maintain the marketing style and appeal of the original text
3. Cultural Adaptation: Adapt content for the target market while preserving meaning
4. Keywords: For keyword fields, provide comma-separated values with NO SPACES after commas for ASO optimization

FIELD-SPECIFIC GUIDELINES:
- App Name (30 chars): Keep brand recognition, may transliterate if needed
- Subtitle (30 chars): Concise value proposition
- Description (4000 chars): Full marketing description with features and benefits
- Keywords (100 chars): Comma-separated, search-optimized terms
- Promotional Text (170 chars): Compelling short marketing message
- What's New (4000 chars): Version update highlights

TRANSLATION PRINCIPLES:
- Natural Language Flow: Translations MUST feel natural to native speakers of the target language
  * This is CRITICAL for user engagement and conversion rates
  * Avoid literal translations that sound robotic or foreign
  * Use expressions and phrasing that locals would naturally use
- Preserve brand voice and personality
- Use native expressions and idioms when appropriate
- Optimize for local App Store search algorithms
- Ensure cultural relevance and sensitivity
- Maintain technical accuracy for feature descriptions

ABSOLUTE CHARACTER LIMIT ENFORCEMENT:
- If character limit is specified, your translation MUST be within that limit
- CHARACTER LIMITS INCLUDE ALL SPACES, PUNCTUATION, AND SPECIAL CHARACTERS
- Count every single character including spaces between words carefully before responding
- If translation exceeds limit, use these strategies IN ORDER:
  1. Remove unnecessary words (articles, modifiers) while preserving meaning
  2. Use shorter synonyms or equivalent expressions
  3. Rephrase sentences more concisely
  4. NEVER sacrifice core meaning or context for length
- Do not add ellipsis (...) at the end unless the original text has it
- For keywords: Format as "word1,word2,word3" (no spaces after commas)
- Focus on creating the most impactful message within the constraints

CRITICAL: If you cannot stay within character limits while preserving meaning, prioritize meaning over strict length compliance, but inform about the issue."""
        
        with open(self.instructions_file, "w") as f:
            f.write(instructions)
    
    def load_providers(self) -> Dict[str, Any]:
        """Load available AI providers configuration."""
        with open(self.providers_file, "r") as f:
            return json.load(f)

    def save_providers(self, providers: Dict[str, Any]) -> None:
        """Persist providers configuration (models, defaults)."""
        with open(self.providers_file, "w") as f:
            json.dump(providers, f, indent=2)
    
    def load_api_keys(self) -> Dict[str, Any]:
        """Load API keys configuration."""
        with open(self.api_keys_file, "r") as f:
            return json.load(f)
    
    def save_api_keys(self, api_keys: Dict[str, Any]):
        """Save API keys configuration."""
        with open(self.api_keys_file, "w") as f:
            json.dump(api_keys, f, indent=2)
    
    def load_instructions(self) -> str:
        """Load translation instructions."""
        with open(self.instructions_file, "r") as f:
            return f.read()
    
    def get_app_store_config(self) -> Optional[Dict[str, str]]:
        """Get App Store Connect configuration."""
        api_keys = self.load_api_keys()
        asc_config = api_keys.get("app_store_connect", {})
        
        # Require key_id and issuer_id; private_key_path can be resolved via default directory
        key_id = asc_config.get("key_id")
        issuer_id = asc_config.get("issuer_id")
        if key_id and issuer_id:
            return asc_config
        return None
    
    def get_ai_provider_key(self, provider: str) -> Optional[str]:
        """Get API key for specific AI provider."""
        # Environment variables take precedence over saved config
        env_names = {
            "openai": ["OPENAI_API_KEY"],
            "anthropic": ["ANTHROPIC_API_KEY"],
            "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GEMINI_API_KEY"],
        }
        for var in env_names.get(provider, []):
            val = os.environ.get(var)
            if val:
                return val.strip()

        # Fallback to config file
        api_keys = self.load_api_keys()
        return api_keys.get("ai_providers", {}).get(provider)

    # --- Provider defaults helpers ---
    def get_default_ai_provider(self) -> Optional[str]:
        """Return configured default provider name, if any and non-empty."""
        cfg = self.load_providers()
        name = cfg.get("default_provider")
        return name or None

    def set_default_ai_provider(self, provider_name: Optional[str]) -> None:
        """Set default provider (None or empty string to clear)."""
        cfg = self.load_providers()
        cfg["default_provider"] = provider_name or ""
        self.save_providers(cfg)

    def list_provider_models(self, provider_name: str) -> Optional[list]:
        cfg = self.load_providers()
        prov = cfg.get(provider_name)
        if isinstance(prov, dict):
            return prov.get("models")
        return None

    def get_default_model(self, provider_name: str) -> Optional[str]:
        cfg = self.load_providers()
        prov = cfg.get(provider_name)
        if isinstance(prov, dict):
            model = prov.get("default_model")
            return model or None
        return None

    def set_default_model(self, provider_name: str, model: str) -> bool:
        """Set default model for a provider. Returns True on success."""
        cfg = self.load_providers()
        prov = cfg.get(provider_name)
        if not isinstance(prov, dict):
            return False
        models = prov.get("models", [])
        if models and model not in models:
            return False
        prov["default_model"] = model
        cfg[provider_name] = prov
        self.save_providers(cfg)
        return True

    # --- Prompt refinement helpers ---
    def get_prompt_refinement(self) -> str:
        """Return configured global prompt refinement phrase, or empty string."""
        try:
            cfg = self.load_providers()
            val = cfg.get("prompt_refinement", "")
            return val or ""
        except Exception:
            return ""

    def set_prompt_refinement(self, phrase: str) -> None:
        cfg = self.load_providers()
        cfg["prompt_refinement"] = phrase or ""
        self.save_providers(cfg)
