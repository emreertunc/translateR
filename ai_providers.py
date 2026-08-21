"""
AI Provider System

Handles integration with multiple AI providers for translation services.
Author: Emre Ertunç
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import requests
import os
from ai_logger import log_ai_request, log_ai_response, log_character_limit_retry
from http_client import request_with_retries
from prompt_builder import build_translation_prompt


OPENAI_MAX_OUTPUT_TOKENS = 25_000
OPENAI_RETRYABLE_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})


def _extract_payload_error(payload: Any) -> Optional[str]:
    """Return the most useful error detail from a provider payload."""
    if not isinstance(payload, dict):
        return str(payload) if payload else None

    error = payload.get("error")
    if isinstance(error, dict):
        for key in ("message", "code", "type"):
            if error.get(key):
                detail = str(error[key]).strip()
                if detail:
                    return detail
    elif error:
        detail = str(error).strip()
        if detail:
            return detail

    for key in ("message", "code", "type"):
        if payload.get(key):
            detail = str(payload[key]).strip()
            if detail:
                return detail
    return None


def _extract_error_message(response: requests.Response) -> str:
    """Return provider error message with API body when available."""
    try:
        payload = response.json()
    except ValueError:
        payload = None

    message = _extract_payload_error(payload)
    if message:
        return message

    text = (response.text or "").strip()
    return text[:400] if text else f"HTTP {response.status_code}"


class AIProvider(ABC):
    """Abstract base class for AI translation providers."""
    
    @abstractmethod
    def translate(self, text: str, target_language: str, 
                  max_length: Optional[int] = None, 
                  is_keywords: bool = False,
                  seed: Optional[int] = None,
                  refinement: Optional[str] = None,
                  instructions: Optional[str] = None) -> str:
        """
        Translate text to target language.
        
        Args:
            text: Text to translate
            target_language: Target language name
            max_length: Maximum character length for translation
            is_keywords: Whether the text is keywords (affects formatting)
            seed: Optional deterministic seed (provider support varies)
            refinement: Optional extra translation guidance
            instructions: Base translation instructions loaded from config
            
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
                  is_keywords: bool = False,
                  seed: Optional[int] = None,
                  refinement: Optional[str] = None,
                  instructions: Optional[str] = None) -> str:
        """Translate using Anthropic Claude."""
        _ = seed

        # Log the request
        log_ai_request("Anthropic Claude", self.model, text, target_language, max_length, is_keywords)
        base_instructions = instructions if instructions is not None else getattr(self, "instructions", "")
        effective_refinement = refinement if refinement is not None else getattr(self, "refinement", None)
        
        try:
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01"
            }
            
            system_message = build_translation_prompt(
                base_instructions,
                target_language,
                max_length=max_length,
                is_keywords=is_keywords,
                refinement=effective_refinement,
            )
            
            data = {
                "model": self.model,
                "system": system_message,
                "max_tokens": 1000,
                "messages": [
                    {"role": "user", "content": text}
                ]
            }
            
            response = request_with_retries(
                "POST", url, headers=headers, json=data, max_retries=2, retry_post=True
            )
            if not response.ok:
                message = _extract_error_message(response)
                raise ValueError(f"Anthropic API error ({response.status_code}): {message}")
            
            response_data = response.json()
            
            if "content" in response_data and isinstance(response_data["content"], list):
                translated_text = response_data["content"][0]["text"]
            else:
                raise ValueError("Unexpected API response format")
            
            # Check character limit and retry if needed
            if max_length and len(translated_text) > max_length:
                log_character_limit_retry("Anthropic Claude", len(translated_text), max_length)
                
                system_message = build_translation_prompt(
                    base_instructions,
                    target_language,
                    max_length=max_length,
                    is_keywords=is_keywords,
                    refinement=effective_refinement,
                    retry_for_length=True,
                )
                data["system"] = system_message
                
                response = request_with_retries(
                    "POST", url, headers=headers, json=data, max_retries=2, retry_post=True
                )
                if not response.ok:
                    message = _extract_error_message(response)
                    raise ValueError(f"Anthropic API error ({response.status_code}): {message}")
                response_data = response.json()
                translated_text = response_data["content"][0]["text"]
            
            # Log successful response
            log_ai_response("Anthropic Claude", translated_text, success=True)
            return translated_text.strip()
            
        except Exception as e:
            # Log error response
            log_ai_response("Anthropic Claude", "", success=False, error=str(e))
            raise Exception(f"Anthropic translation failed: {str(e)}")
    
    def get_name(self) -> str:
        return "Anthropic Claude"


class OpenAIProvider(AIProvider):
    """OpenAI GPT provider."""
    
    def __init__(self, api_key: str, model: str = None):
        self.api_key = api_key
        self.model = model

    def _uses_responses_api(self) -> bool:
        """Use Responses API for GPT-5 family models."""
        return bool(self.model) and self.model.startswith("gpt-5")

    def _build_request_payload(self, system_message: str, text: str) -> Dict[str, Any]:
        """Build request payload based on selected OpenAI API."""
        if self._uses_responses_api():
            return {
                "model": self.model,
                "input": [
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": system_message}]
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": text}]
                    }
                ],
                "max_output_tokens": OPENAI_MAX_OUTPUT_TOKENS,
                "reasoning": {"effort": "medium"},
                "store": False,
            }

        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": text}
            ],
            "max_tokens": 1000,
            "temperature": 0.7
        }

    def _extract_response_text(self, response_data: Dict[str, Any]) -> str:
        """Extract translated text from either Responses or Chat Completions format."""
        if self._uses_responses_api():
            status = response_data.get("status")
            if status == "incomplete":
                details = response_data.get("incomplete_details")
                reason = details.get("reason") if isinstance(details, dict) else None
                raise ValueError(
                    f"OpenAI response incomplete: {reason or 'unknown reason'}"
                )
            if status == "failed":
                message = _extract_payload_error(response_data)
                raise ValueError(f"OpenAI response failed: {message or 'unknown error'}")
            if status and status != "completed":
                raise ValueError(f"OpenAI response not completed: {status}")

            output_text = response_data.get("output_text")
            if output_text:
                return str(output_text)

            for item in response_data.get("output", []):
                if not isinstance(item, dict):
                    continue

                item_type = item.get("type")
                if item_type in ("output_text", "text") and item.get("text"):
                    return str(item["text"])

                if item_type == "message":
                    for content in item.get("content", []):
                        if not isinstance(content, dict):
                            continue
                        text_value = content.get("text") or content.get("value")
                        if text_value:
                            return str(text_value)

            raise ValueError("Unexpected Responses API format")

        if "choices" in response_data and len(response_data["choices"]) > 0:
            return response_data["choices"][0]["message"]["content"]

        raise ValueError("Unexpected Chat Completions API format")
    
    def translate(self, text: str, target_language: str, 
                  max_length: Optional[int] = None, 
                  is_keywords: bool = False,
                  seed: Optional[int] = None,
                  refinement: Optional[str] = None,
                  instructions: Optional[str] = None) -> str:
        """Translate using OpenAI GPT."""
        _ = seed

        # Log the request
        log_ai_request("OpenAI GPT", self.model, text, target_language, max_length, is_keywords)
        base_instructions = instructions if instructions is not None else getattr(self, "instructions", "")
        effective_refinement = refinement if refinement is not None else getattr(self, "refinement", None)
        
        try:
            url = (
                "https://api.openai.com/v1/responses"
                if self._uses_responses_api()
                else "https://api.openai.com/v1/chat/completions"
            )
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            system_message = build_translation_prompt(
                base_instructions,
                target_language,
                max_length=max_length,
                is_keywords=is_keywords,
                refinement=effective_refinement,
            )
            
            data = self._build_request_payload(system_message, text)
            
            response = request_with_retries(
                "POST",
                url,
                headers=headers,
                json=data,
                max_retries=2,
                retry_status_codes=OPENAI_RETRYABLE_STATUS_CODES,
            )
            if not response.ok:
                message = _extract_error_message(response)
                raise ValueError(f"OpenAI API error ({response.status_code}): {message}")
            
            response_data = response.json()
            translated_text = self._extract_response_text(response_data)
            
            # Check character limit and retry if needed
            if max_length and len(translated_text) > max_length:
                log_character_limit_retry("OpenAI GPT", len(translated_text), max_length)
                
                system_message = build_translation_prompt(
                    base_instructions,
                    target_language,
                    max_length=max_length,
                    is_keywords=is_keywords,
                    refinement=effective_refinement,
                    retry_for_length=True,
                )
                data = self._build_request_payload(system_message, text)
                
                response = request_with_retries(
                    "POST",
                    url,
                    headers=headers,
                    json=data,
                    max_retries=2,
                    retry_status_codes=OPENAI_RETRYABLE_STATUS_CODES,
                )
                if not response.ok:
                    message = _extract_error_message(response)
                    raise ValueError(f"OpenAI API error ({response.status_code}): {message}")
                response_data = response.json()
                translated_text = self._extract_response_text(response_data)
            
            # Log successful response
            log_ai_response("OpenAI GPT", translated_text, success=True)
            return translated_text.strip()
            
        except Exception as e:
            # Log error response
            log_ai_response("OpenAI GPT", "", success=False, error=str(e))
            raise Exception(f"OpenAI translation failed: {str(e)}")
    
    def get_name(self) -> str:
        return "OpenAI GPT"


class GoogleGeminiProvider(AIProvider):
    """Google Gemini provider."""
    
    def __init__(self, api_key: str, model: str = None):
        self.api_key = api_key
        self.model = model

    def _candidate_api_versions(self) -> List[str]:
        """
        Return API versions to try.
        Gemini 3 family is currently exposed via v1beta for many keys.
        """
        if self.model and self.model.startswith("gemini-3"):
            return ["v1beta", "v1"]
        return ["v1", "v1beta"]

    def _post_generate_content(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Call Gemini API with version fallback for model availability differences."""
        last_error: Optional[str] = None

        for version in self._candidate_api_versions():
            url = (
                f"https://generativelanguage.googleapis.com/{version}/"
                f"models/{self.model}:generateContent?key={self.api_key}"
            )
            response = request_with_retries(
                "POST",
                url,
                headers={"Content-Type": "application/json"},
                json=data,
                max_retries=2,
                retry_post=True,
            )
            if response.ok:
                return response.json()

            # Model may exist only in the other API version; retry there on 404.
            if response.status_code == 404:
                last_error = f"{version}: {_extract_error_message(response)}"
                continue

            message = _extract_error_message(response)
            raise ValueError(f"Google Gemini API error ({response.status_code}, {version}): {message}")

        raise ValueError(f"Google Gemini model unavailable: {self.model} ({last_error or 'no details'})")
    
    def translate(self, text: str, target_language: str, 
                  max_length: Optional[int] = None, 
                  is_keywords: bool = False,
                  seed: Optional[int] = None,
                  refinement: Optional[str] = None,
                  instructions: Optional[str] = None) -> str:
        """Translate using Google Gemini."""
        _ = seed

        # Log the request
        log_ai_request("Google Gemini", self.model, text, target_language, max_length, is_keywords)
        base_instructions = instructions if instructions is not None else getattr(self, "instructions", "")
        effective_refinement = refinement if refinement is not None else getattr(self, "refinement", None)
        
        try:
            prompt = build_translation_prompt(
                base_instructions,
                target_language,
                max_length=max_length,
                is_keywords=is_keywords,
                refinement=effective_refinement,
            )
            prompt += f"\n\nText to translate: {text}"
            
            data = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }],
                "generationConfig": {
                    "maxOutputTokens": 8000
                }
            }
            
            response_data = self._post_generate_content(data)
            
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
                log_character_limit_retry("Google Gemini", len(translated_text), max_length)
                
                prompt = build_translation_prompt(
                    base_instructions,
                    target_language,
                    max_length=max_length,
                    is_keywords=is_keywords,
                    refinement=effective_refinement,
                    retry_for_length=True,
                )
                prompt += f"\n\nText to translate: {text}"
                data["contents"][0]["parts"][0]["text"] = prompt
                
                response_data = self._post_generate_content(data)
                translated_text = response_data["candidates"][0]["content"]["parts"][0]["text"]
            
            # Log successful response
            log_ai_response("Google Gemini", translated_text, success=True)
            return translated_text.strip()
            
        except Exception as e:
            # Log error response
            log_ai_response("Google Gemini", "", success=False, error=str(e))
            raise Exception(f"Google Gemini translation failed: {str(e)}")
    
    def get_name(self) -> str:
        return "Google Gemini"


class OpenRouterProvider(AIProvider):
    """OpenRouter AI provider - provides access to many AI models through a unified API."""
    
    def __init__(self, api_key: str, model: str = None):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1"
    
    def _build_request_payload(self, system_message: str, text: str) -> Dict[str, Any]:
        """Build request payload for OpenRouter API."""
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": text}
            ],
            "max_tokens": 8000,
            "temperature": 0.7
        }
    
    def _extract_response_text(self, response_data: Dict[str, Any]) -> str:
        """Extract translated text from OpenRouter response."""
        if "choices" in response_data and len(response_data["choices"]) > 0:
            return response_data["choices"][0]["message"]["content"]
        raise ValueError("Unexpected OpenRouter API response format")
    
    def translate(self, text: str, target_language: str, 
                  max_length: Optional[int] = None, 
                  is_keywords: bool = False,
                  seed: Optional[int] = None,
                  refinement: Optional[str] = None,
                  instructions: Optional[str] = None) -> str:
        """Translate using OpenRouter."""
        _ = seed

        # Log the request
        log_ai_request("OpenRouter", self.model, text, target_language, max_length, is_keywords)
        base_instructions = instructions if instructions is not None else getattr(self, "instructions", "")
        effective_refinement = refinement if refinement is not None else getattr(self, "refinement", None)
        
        try:
            url = f"{self.base_url}/chat/completions"
            
            # OpenRouter requires specific headers for tracking
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            system_message = build_translation_prompt(
                base_instructions,
                target_language,
                max_length=max_length,
                is_keywords=is_keywords,
                refinement=effective_refinement,
            )
            
            data = self._build_request_payload(system_message, text)
            
            response = request_with_retries(
                "POST", url, headers=headers, json=data, max_retries=2, retry_post=True
            )
            if not response.ok:
                message = _extract_error_message(response)
                raise ValueError(f"OpenRouter API error ({response.status_code}): {message}")
            
            response_data = response.json()
            translated_text = self._extract_response_text(response_data)
            
            # Check character limit and retry if needed
            if max_length and len(translated_text) > max_length:
                log_character_limit_retry("OpenRouter", len(translated_text), max_length)
                
                system_message = build_translation_prompt(
                    base_instructions,
                    target_language,
                    max_length=max_length,
                    is_keywords=is_keywords,
                    refinement=effective_refinement,
                    retry_for_length=True,
                )
                data = self._build_request_payload(system_message, text)
                
                response = request_with_retries(
                    "POST", url, headers=headers, json=data, max_retries=2, retry_post=True
                )
                if not response.ok:
                    message = _extract_error_message(response)
                    raise ValueError(f"OpenRouter API error ({response.status_code}): {message}")
                response_data = response.json()
                translated_text = self._extract_response_text(response_data)
            
            # Log successful response
            log_ai_response("OpenRouter", translated_text, success=True)
            return translated_text.strip()
            
        except Exception as e:
            # Log error response
            log_ai_response("OpenRouter", "", success=False, error=str(e))
            raise Exception(f"OpenRouter translation failed: {str(e)}")
    
    def get_name(self) -> str:
        return "OpenRouter"


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
