"""
AI Provider System

Handles integration with multiple AI providers for translation services.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import requests
import os


class AIProvider(ABC):
    """Abstract base class for AI translation providers."""
    
    @abstractmethod
    def translate(self, text: str, target_language: str, 
                  max_length: Optional[int] = None, 
                  is_keywords: bool = False) -> str:
        """
        Translate text to target language.
        
        Args:
            text: Text to translate
            target_language: Target language name
            max_length: Maximum character length for translation
            is_keywords: Whether the text is keywords (affects formatting)
            
        Returns:
            Translated text
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Get provider name."""
        pass


class AnthropicProvider(AIProvider):
    """Anthropic Claude AI provider."""
    
    def __init__(self, api_key: str, model: str = None):
        self.api_key = api_key
        self.model = model
    
    def translate(self, text: str, target_language: str, 
                  max_length: Optional[int] = None, 
                  is_keywords: bool = False) -> str:
        """Translate using Anthropic Claude."""
        try:
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01"
            }
            
            # Build system message
            system_message = (
                f"You are a professional translator specializing in App Store metadata translation. "
                f"Translate the following text to {target_language}. "
                f"Maintain the marketing tone and style of the original text."
            )
            
            if is_keywords:
                system_message += " For keywords, provide a comma-separated list and keep it concise."
            
            if max_length:
                system_message += (
                    f" CRITICAL: Your translation MUST be {max_length} characters or fewer. "
                    f"Do not add ellipsis (...) at the end. Create a concise but meaningful "
                    f"translation that captures the essence of the original message while "
                    f"staying within the character limit."
                )
            
            data = {
                "model": self.model,
                "system": system_message,
                "max_tokens": 1000,
                "messages": [
                    {"role": "user", "content": text}
                ]
            }
            
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            response_data = response.json()
            
            if "content" in response_data and isinstance(response_data["content"], list):
                translated_text = response_data["content"][0]["text"]
            else:
                raise ValueError("Unexpected API response format")
            
            # Check character limit and retry if needed
            if max_length and len(translated_text) > max_length:
                # Try again with even stricter instructions
                system_message += f" The text MUST be under {max_length} characters. Prioritize brevity."
                data["system"] = system_message
                
                response = requests.post(url, headers=headers, json=data)
                response.raise_for_status()
                response_data = response.json()
                translated_text = response_data["content"][0]["text"]
            
            return translated_text
            
        except Exception as e:
            raise Exception(f"Anthropic translation failed: {str(e)}")
    
    def get_name(self) -> str:
        return "Anthropic Claude"


class OpenAIProvider(AIProvider):
    """OpenAI GPT provider."""
    
    def __init__(self, api_key: str, model: str = None):
        self.api_key = api_key
        self.model = model
    
    def translate(self, text: str, target_language: str, 
                  max_length: Optional[int] = None, 
                  is_keywords: bool = False) -> str:
        """Translate using OpenAI GPT."""
        try:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Build system message
            system_message = (
                f"You are a professional translator specializing in App Store metadata translation. "
                f"Translate the following text to {target_language}. "
                f"Maintain the marketing tone and style of the original text."
            )
            
            if is_keywords:
                system_message += " For keywords, provide a comma-separated list and keep it concise."
            
            if max_length:
                system_message += (
                    f" CRITICAL: Your translation MUST be {max_length} characters or fewer. "
                    f"Do not add ellipsis (...) at the end. Create a concise but meaningful "
                    f"translation that captures the essence of the original message while "
                    f"staying within the character limit."
                )
            
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": text}
                ],
                "max_tokens": 1000,
                "temperature": 0.7
            }
            
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            response_data = response.json()
            
            if "choices" in response_data and len(response_data["choices"]) > 0:
                translated_text = response_data["choices"][0]["message"]["content"]
            else:
                raise ValueError("Unexpected API response format")
            
            # Check character limit and retry if needed
            if max_length and len(translated_text) > max_length:
                # Try again with even stricter instructions
                system_message += f" The text MUST be under {max_length} characters. Prioritize brevity."
                data["messages"][0]["content"] = system_message
                
                response = requests.post(url, headers=headers, json=data)
                response.raise_for_status()
                response_data = response.json()
                translated_text = response_data["choices"][0]["message"]["content"]
            
            return translated_text
            
        except Exception as e:
            raise Exception(f"OpenAI translation failed: {str(e)}")
    
    def get_name(self) -> str:
        return "OpenAI GPT"


class GoogleGeminiProvider(AIProvider):
    """Google Gemini provider."""
    
    def __init__(self, api_key: str, model: str = None):
        self.api_key = api_key
        self.model = model
    
    def translate(self, text: str, target_language: str, 
                  max_length: Optional[int] = None, 
                  is_keywords: bool = False) -> str:
        """Translate using Google Gemini."""
        try:
            url = f"https://generativelanguage.googleapis.com/v1/models/{self.model}:generateContent?key={self.api_key}"
            headers = {
                "Content-Type": "application/json"
            }
            
            # Build prompt
            prompt = (
                f"You are a professional translator specializing in App Store metadata translation. "
                f"Translate the following text to {target_language}. "
                f"Maintain the marketing tone and style of the original text."
            )
            
            if is_keywords:
                prompt += " For keywords, provide a comma-separated list and keep it concise."
            
            if max_length:
                prompt += (
                    f" CRITICAL: Your translation MUST be {max_length} characters or fewer. "
                    f"Do not add ellipsis (...) at the end. Create a concise but meaningful "
                    f"translation that captures the essence of the original message while "
                    f"staying within the character limit."
                )
            
            prompt += f"\n\nText to translate: {text}"
            
            data = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 8000
                }
            }
            
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            response_data = response.json()
            
            if ("candidates" in response_data and 
                len(response_data["candidates"]) > 0 and
                "content" in response_data["candidates"][0] and
                "parts" in response_data["candidates"][0]["content"] and
                len(response_data["candidates"][0]["content"]["parts"]) > 0):
                translated_text = response_data["candidates"][0]["content"]["parts"][0]["text"]
            elif ("candidates" in response_data and 
                  len(response_data["candidates"]) > 0 and
                  response_data["candidates"][0].get("finishReason") == "MAX_TOKENS"):
                raise ValueError("Translation too long - exceeded token limit. Try shorter text.")
            else:
                raise ValueError("Unexpected API response format")
            
            # Check character limit and retry if needed
            if max_length and len(translated_text) > max_length:
                # Try again with even stricter instructions
                prompt += f" The text MUST be under {max_length} characters. Prioritize brevity."
                data["contents"][0]["parts"][0]["text"] = prompt
                
                response = requests.post(url, headers=headers, json=data)
                response.raise_for_status()
                response_data = response.json()
                translated_text = response_data["candidates"][0]["content"]["parts"][0]["text"]
            
            return translated_text
            
        except Exception as e:
            raise Exception(f"Google Gemini translation failed: {str(e)}")
    
    def get_name(self) -> str:
        return "Google Gemini"


class AIProviderManager:
    """Manages multiple AI providers and handles provider selection."""
    
    def __init__(self):
        self.providers: Dict[str, AIProvider] = {}
    
    def add_provider(self, name: str, provider: AIProvider):
        """Add an AI provider."""
        self.providers[name] = provider
    
    def get_provider(self, name: str) -> Optional[AIProvider]:
        """Get a specific AI provider."""
        return self.providers.get(name)
    
    def list_providers(self) -> List[str]:
        """List all available provider names."""
        return list(self.providers.keys())