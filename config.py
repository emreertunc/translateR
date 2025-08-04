"""
Configuration Management

Handles loading and saving of configuration files including API keys,
provider settings, and user preferences.
"""

import json
import os
from typing import Dict, Any, Optional
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
        
        self._ensure_config_files()
    
    def _ensure_config_files(self):
        """Create default configuration files if they don't exist."""
        if not self.providers_file.exists():
            self._create_default_providers()
        
        if not self.api_keys_file.exists():
            self._create_default_api_keys()
        
        if not self.instructions_file.exists():
            self._create_default_instructions()
    
    def _create_default_providers(self):
        """Create default providers configuration."""
        default_providers = {
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
                    "gpt-4.1",
                    "gpt-4o",
                    "gpt-4o-mini", 
                    "gpt-4-turbo",
                    "gpt-4",
                    "gpt-3.5-turbo"
                ],
                "default_model": "gpt-4.1"
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
                "google": ""
            }
        }
        
        with open(self.api_keys_file, "w") as f:
            json.dump(default_keys, f, indent=2)
    
    def _create_default_instructions(self):
        """Create default translation instructions."""
        instructions = """You are a professional translator specializing in App Store metadata translation.

CRITICAL REQUIREMENTS:
1. Character Limits: NEVER exceed the specified character limit for any field
2. Marketing Tone: Maintain the marketing style and appeal of the original text
3. Cultural Adaptation: Adapt content for the target market while preserving meaning
4. Keywords: For keyword fields, provide comma-separated values optimized for App Store search

FIELD-SPECIFIC GUIDELINES:
- App Name (30 chars): Keep brand recognition, may transliterate if needed
- Subtitle (30 chars): Concise value proposition
- Description (4000 chars): Full marketing description with features and benefits
- Keywords (100 chars): Comma-separated, search-optimized terms
- Promotional Text (170 chars): Compelling short marketing message
- What's New (4000 chars): Version update highlights

TRANSLATION PRINCIPLES:
- Preserve brand voice and personality
- Use native expressions and idioms when appropriate
- Optimize for local App Store search algorithms
- Ensure cultural relevance and sensitivity
- Maintain technical accuracy for feature descriptions

If the character limit is specified, your translation MUST be within that limit.
Do not add ellipsis (...) at the end unless the original text has it.
Focus on creating the most impactful message within the constraints."""
        
        with open(self.instructions_file, "w") as f:
            f.write(instructions)
    
    def load_providers(self) -> Dict[str, Any]:
        """Load available AI providers configuration."""
        with open(self.providers_file, "r") as f:
            return json.load(f)
    
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
        
        if all(asc_config.values()):
            return asc_config
        return None
    
    def get_ai_provider_key(self, provider: str) -> Optional[str]:
        """Get API key for specific AI provider."""
        api_keys = self.load_api_keys()
        return api_keys.get("ai_providers", {}).get(provider)