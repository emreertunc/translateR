"""
Configuration Management

Handles loading and saving of configuration files including API keys,
provider settings, and user preferences.
"""

import json
import os
from typing import Dict, Any, Optional, List
from pathlib import Path


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
        self.saved_apps_file = self.config_dir / "saved_apps.json"
        
        self._ensure_config_files()
    
    def _ensure_config_files(self):
        """Create default configuration files if they don't exist."""
        if not self.providers_file.exists():
            self._create_default_providers()
        
        if not self.api_keys_file.exists():
            self._create_default_api_keys()
        
        if not self.instructions_file.exists():
            self._create_default_instructions()
        
        if not self.saved_apps_file.exists():
            self._create_default_saved_apps()
    
    def _create_default_providers(self):
        """Create default providers configuration."""
        default_providers = {
            "default_provider": "",
            "prompt_refinement": "",
            "anthropic": {
                "name": "Anthropic Claude",
                "class": "AnthropicProvider",
                "models": [
                    "claude-sonnet-4-6",
                    "claude-opus-4-6",
                    "claude-opus-4-5-20251101",
                    "claude-sonnet-4-5-20250929",
                    "claude-haiku-4-5-20251001",
                    "claude-opus-4-1-20250805",
                    "claude-sonnet-4-20250514",
                    "claude-opus-4-20250514",
                    "claude-3-haiku-20240307"
                ],
                "default_model": "claude-sonnet-4-6"
            },
            "openai": {
                "name": "OpenAI GPT",
                "class": "OpenAIProvider", 
                "models": [
                    "gpt-5.2",
                    "gpt-5.1",
                    "gpt-5",
                    "gpt-5-2025-08-07",
                    "gpt-5-mini",
                    "gpt-5-mini-2025-08-07",
                    "gpt-5-nano",
                    "gpt-5-nano-2025-08-07",
                ],
                "default_model": "gpt-5.2"
            },
            "google": {
                "name": "Google Gemini",
                "class": "GoogleGeminiProvider",
                "models": [
                    "gemini-3.1-pro-preview",
                    "gemini-3-flash-preview",
                    "gemini-2.5-pro",
                    "gemini-2.5-flash",
                    "gemini-2.5-flash-lite"
                ],
                "default_model": "gemini-3-flash-preview"
            },
            "openrouter": {
                "name": "OpenRouter",
                "class": "OpenRouterProvider",
                "models": [
                    "openai/gpt-5.4",
                    "openai/gpt-5.4-pro",
                    "openai/gpt-5.3-codex",
                    "openai/gpt-4o-mini",
                    "openai/gpt-5.2",
                    "openai/gpt-5-nano",
                    "openai/gpt-oss-120b",
                    "anthropic/claude-haiku-4.5",
                    "anthropic/claude-opus-4.6",
                    "anthropic/claude-sonnet-4.6",
                    "google/gemini-3.1-flash-lite-preview",
                    "google/gemini-3.1-pro-preview",
                    "meta-llama/llama-4-maverick",
                    "meta-llama/llama-guard-4-12b",
                    "mistralai/mistral-small-creative",
                    "mistralai/ministral-14b-2512",
                    "deepseek/deepseek-v3.2-speciale",
                    "deepseek/deepseek-v3.2",
                    "deepseek/deepseek-v3.2-exp",
                    "x-ai/grok-4.1-fast",
                    "x-ai/grok-4-fast",
                    "x-ai/grok-code-fast-1"
                ],
                "default_model": "google/gemini-3.1-pro-preview"
            },
            "nvidia": {
                "name": "NVIDIA NIM",
                "class": "NVIDIAProvider",
                "models": [
                    "mistralai/mistral-large-3-675b-instruct-2512",
                    "mistralai/mistral-medium-3.5-128b",
                    "mistralai/ministral-14b-instruct-2512",
                    "meta/llama-3.1-405b-instruct",
                    "meta/llama-3.1-70b-instruct",
                    "nvidia/llama-3.1-nemotron-70b-instruct"
                ],
                "default_model": "mistralai/mistral-large-3-675b-instruct-2512"
            }
        }
        
        with open(self.providers_file, "w") as f:
            json.dump(default_providers, f, indent=2)
    
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
                "google": "",
                "openrouter": "",
                "nvidia": ""
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

    def _create_default_saved_apps(self):
        """Create default saved apps file."""
        with open(self.saved_apps_file, "w") as f:
            json.dump({}, f, indent=2)
    
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

    def load_saved_apps(self) -> Dict[str, str]:
        """Load saved app IDs mapped to app names."""
        try:
            with open(self.saved_apps_file, "r") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
        return {}

    def save_saved_apps(self, saved_apps: Dict[str, str]):
        """Save app IDs mapped to app names."""
        tmp_path = self.saved_apps_file.with_suffix(self.saved_apps_file.suffix + ".tmp")
        with open(tmp_path, "w") as f:
            json.dump(saved_apps, f, indent=2)
        os.replace(tmp_path, self.saved_apps_file)
    
    def get_app_store_config(self) -> Optional[Dict[str, str]]:
        """Get App Store Connect configuration."""
        api_keys = self.load_api_keys()
        asc_config = api_keys.get("app_store_connect", {})
        
        if all(asc_config.values()):
            return asc_config
        return None
    
    def get_ai_provider_key(self, provider: str) -> Optional[str]:
        """Get API key for specific AI provider."""
        api_keys = self.load_api_keys()
        return api_keys.get("ai_providers", {}).get(provider)

    def get_default_ai_provider(self) -> Optional[str]:
        """Return configured default provider name, if any."""
        cfg = self.load_providers()
        default_provider = cfg.get("default_provider")
        return default_provider or None

    def set_default_ai_provider(self, provider_name: Optional[str]) -> None:
        """Set default provider (None or empty string clears it)."""
        cfg = self.load_providers()
        cfg["default_provider"] = provider_name or ""
        self.save_providers(cfg)

    def list_provider_models(self, provider_name: str) -> List[str]:
        """Return model list configured for a provider."""
        cfg = self.load_providers()
        provider = cfg.get(provider_name)
        if isinstance(provider, dict):
            models = provider.get("models", [])
            if isinstance(models, list):
                return [str(model) for model in models]
        return []

    def get_default_model(self, provider_name: str) -> Optional[str]:
        """Return default model for provider if configured."""
        cfg = self.load_providers()
        provider = cfg.get(provider_name)
        if isinstance(provider, dict):
            model = provider.get("default_model")
            return str(model) if model else None
        return None

    def set_default_model(self, provider_name: str, model: str) -> bool:
        """Set default model for provider, returns True on success."""
        cfg = self.load_providers()
        provider = cfg.get(provider_name)
        if not isinstance(provider, dict):
            return False

        models = provider.get("models", [])
        if isinstance(models, list) and models and model not in models:
            return False

        provider["default_model"] = model
        cfg[provider_name] = provider
        self.save_providers(cfg)
        return True

    def get_prompt_refinement(self) -> str:
        """Return configured global prompt refinement phrase, or empty string."""
        cfg = self.load_providers()
        return str(cfg.get("prompt_refinement", "") or "")

    def set_prompt_refinement(self, phrase: str) -> None:
        """Persist global prompt refinement phrase."""
        cfg = self.load_providers()
        cfg["prompt_refinement"] = phrase or ""
        self.save_providers(cfg)
