"""
AI Provider System

Handles integration with multiple AI providers for translation services.
Author: Emre Ertunç
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import requests
import os
import time
from ai_logger import log_ai_request, log_ai_response, log_character_limit_retry
import threading


def _extract_error_message(response: requests.Response) -> str:
    """Return provider error message with API body when available."""
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            message = err.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()

    text = (response.text or "").strip()
    return text[:400] if text else f"HTTP {response.status_code}"


class AIProvider(ABC):
    """Abstract base class for AI translation providers."""
    
    @abstractmethod
    def translate(self, text: str, target_language: str, 
                  max_length: Optional[int] = None, 
                  is_keywords: bool = False,
                  seed: Optional[int] = None,
                  refinement: Optional[str] = None) -> str:
        """
        Translate text to target language.
        
        Args:
            text: Text to translate
            target_language: Target language name
            max_length: Maximum character length for translation
            is_keywords: Whether the text is keywords (affects formatting)
            seed: Optional deterministic seed (provider support varies)
            refinement: Optional extra translation guidance
            
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
                  refinement: Optional[str] = None) -> str:
        """Translate using Anthropic Claude."""
        _ = seed

        # Log the request
        log_ai_request("Anthropic Claude", self.model, text, target_language, max_length, is_keywords)
        
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

            if refinement:
                system_message += f" Additional guidance: {refinement}"
            
            if max_length:
                system_message += (
                    f" CRITICAL: Your translation MUST be EXACTLY {max_length} characters or fewer "
                    f"INCLUDING ALL SPACES, PUNCTUATION, AND SPECIAL CHARACTERS. Count every single "
                    f"character including spaces between words. Do not add ellipsis (...) at the end. "
                    f"Create a concise but meaningful translation that captures the essence of the "
                    f"original message while staying within the character limit."
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
            if not response.ok:
                message = _extract_error_message(response)
                raise ValueError(f"Anthropic API error ({response.status_code}): {message}")
            
            response_data = response.json()
            
            if "content" in response_data and isinstance(response_data["content"], list) and len(response_data["content"]) > 0:
                translated_text = response_data["content"][0].get("text")
                if translated_text is None:
                    raise ValueError("Anthropic returned empty content")
            else:
                raise ValueError("Unexpected API response format")
            
            # Check character limit and retry if needed (up to 8 times)
            retry_count = 0
            max_retries = 8
            
            while max_length and len(translated_text) > max_length and retry_count < max_retries:
                retry_count += 1
                # Decrease the effective max length by 5 for each retry to force more aggressive shortening
                dynamic_max_length = max(10, max_length - (retry_count * 5))
                log_character_limit_retry("Anthropic Claude", len(translated_text), max_length)
                
                # Try again with even stricter instructions
                if retry_count == max_retries:
                    system_message += f" FINAL WARNING: THE PREVIOUS OUTPUT WAS TOO LONG. YOU MUST OUTPUT LESS THAN {dynamic_max_length} CHARACTERS. CUT THE TEXT AGGRESSIVELY."
                else:
                    system_message += f" The text MUST be under {dynamic_max_length} characters. Count every character. Prioritize brevity."
                
                data["system"] = system_message
                
                response = requests.post(url, headers=headers, json=data)
                if not response.ok:
                    message = _extract_error_message(response)
                    raise ValueError(f"Anthropic API error ({response.status_code}): {message}")
                
                response_data = response.json()
                translated_text = response_data["content"][0]["text"]
            
            # If it's STILL too long after retries, truncate as a absolute last resort to prevent API crash
            if max_length and len(translated_text) > max_length:
                from utils import print_warning
                print_warning(f"  ⚠️  Translation still too long ({len(translated_text)} chars) after {max_retries} retries. Final truncation to {max_length}.")
                translated_text = translated_text[:max_length]
            
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
                "max_output_tokens": 1000,
                "reasoning": {"effort": "medium"}
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

    def _parse_openai_response(self, response_data: Dict[str, Any]) -> str:
        """Extract translated text from either Responses or Chat Completions format."""
        if self._uses_responses_api():
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
            msg = response_data["choices"][0].get("message", {})
            content = msg.get("content")
            if content is not None:
                return str(content)
            
            # Check for refusal (common in newer models)
            refusal = msg.get("refusal")
            if refusal:
                raise ValueError(f"AI Model Refusal: {refusal}")
            
            raise ValueError("AI provider returned empty content")

        raise ValueError("Unexpected Chat Completions API format")
    
    def translate(self, text: str, target_language: str, 
                  max_length: Optional[int] = None, 
                  is_keywords: bool = False,
                  seed: Optional[int] = None,
                  refinement: Optional[str] = None) -> str:
        """Translate using OpenAI GPT."""
        _ = seed

        # Log the request
        log_ai_request("OpenAI GPT", self.model, text, target_language, max_length, is_keywords)
        
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
            
            # Build system message
            system_message = (
                f"You are a professional translator specializing in App Store metadata translation. "
                f"Translate the following text to {target_language}. "
                f"Maintain the marketing tone and style of the original text."
            )
            
            if is_keywords:
                system_message += " For keywords, provide a comma-separated list and keep it concise."

            if refinement:
                system_message += f" Additional guidance: {refinement}"
            
            if max_length:
                system_message += (
                    f" CRITICAL: Your translation MUST be EXACTLY {max_length} characters or fewer "
                    f"INCLUDING ALL SPACES, PUNCTUATION, AND SPECIAL CHARACTERS. Count every single "
                    f"character including spaces between words. Do not add ellipsis (...) at the end. "
                    f"Create a concise but meaningful translation that captures the essence of the "
                    f"original message while staying within the character limit."
                )
            
            user_content = text
            if max_length:
                user_content = f"{text}\n\nREMINDER: Target language is {target_language}. Max {max_length} chars. ONLY return translation."
            
            data = self._build_request_payload(system_message, user_content)
            
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            response_data = response.json()
            translated_text = self._parse_openai_response(response_data)
            
            # Check character limit and retry if needed (up to 8 times)
            retry_count = 0
            max_retries = 8
            
            while max_length and len(translated_text) > max_length and retry_count < max_retries:
                retry_count += 1
                # Decrease the effective max length by 5 for each retry to force more aggressive shortening
                dynamic_max_length = max(10, max_length - (retry_count * 5))
                log_character_limit_retry("OpenAI GPT", len(translated_text), max_length)
                
                # Try again with even stricter instructions
                if retry_count == max_retries:
                    system_message += f" FINAL WARNING: THE PREVIOUS OUTPUT WAS TOO LONG. YOU MUST OUTPUT LESS THAN {dynamic_max_length} CHARACTERS. CUT THE TEXT AGGRESSIVELY."
                else:
                    system_message += f" The text MUST be under {dynamic_max_length} characters. Count every character. Prioritize brevity."
                
                user_content = text
                if dynamic_max_length:
                    user_content = f"{text}\n\nREMINDER: Target language is {target_language}. Max {dynamic_max_length} chars. ONLY return translation."
                
                data = self._build_request_payload(system_message, user_content)
                
                response = requests.post(url, headers=headers, json=data)
                response.raise_for_status()
                response_data = response.json()
                translated_text = self._parse_openai_response(response_data)
            
            # If it's STILL too long after retries, truncate as a absolute last resort to prevent API crash
            if max_length and len(translated_text) > max_length:
                from utils import print_warning
                print_warning(f"  ⚠️  Translation still too long ({len(translated_text)} chars) after {max_retries} retries. Final truncation to {max_length}.")
                translated_text = translated_text[:max_length]
            
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
            response = requests.post(url, headers={"Content-Type": "application/json"}, json=data)
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
                  refinement: Optional[str] = None) -> str:
        """Translate using Google Gemini."""
        _ = seed

        # Log the request
        log_ai_request("Google Gemini", self.model, text, target_language, max_length, is_keywords)
        
        try:
            # Build prompt
            prompt = (
                f"You are a professional translator specializing in App Store metadata translation. "
                f"Translate the following text to {target_language}. "
                f"Maintain the marketing tone and style of the original text."
            )
            
            if is_keywords:
                prompt += " For keywords, provide a comma-separated list and keep it concise."

            if refinement:
                prompt += f" Additional guidance: {refinement}"
            
            if max_length:
                prompt += (
                    f" CRITICAL: Your translation MUST be EXACTLY {max_length} characters or fewer "
                    f"INCLUDING ALL SPACES, PUNCTUATION, AND SPECIAL CHARACTERS. Count every single "
                    f"character including spaces between words. Do not add ellipsis (...) at the end. "
                    f"Create a concise but meaningful translation that captures the essence of the "
                    f"original message while staying within the character limit."
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
            
            response_data = self._post_generate_content(data)
            
            if ("candidates" in response_data and 
                len(response_data["candidates"]) > 0):
                candidate = response_data["candidates"][0]
                
                # Check if content was blocked
                if candidate.get("finishReason") == "SAFETY":
                    raise ValueError("Google Gemini blocked the response due to safety filters.")
                
                content = candidate.get("content", {})
                parts = content.get("parts", [])
                if parts and parts[0].get("text"):
                    translated_text = parts[0]["text"]
                elif candidate.get("finishReason") == "MAX_TOKENS":
                    raise ValueError("Translation too long - exceeded token limit. Try shorter text.")
                else:
                    raise ValueError(f"Unexpected Gemini response (finishReason: {candidate.get('finishReason')})")
            else:
                raise ValueError("Unexpected API response format: No candidates found")
            
            # Check character limit and retry if needed (up to 8 times)
            retry_count = 0
            max_retries = 8
            
            while max_length and len(translated_text) > max_length and retry_count < max_retries:
                retry_count += 1
                # Decrease the effective max length by 5 for each retry to force more aggressive shortening
                dynamic_max_length = max(10, max_length - (retry_count * 5))
                log_character_limit_retry("Google Gemini", len(translated_text), max_length)
                
                # Try again with even stricter instructions
                if retry_count == max_retries:
                    prompt += f" FINAL WARNING: THE PREVIOUS OUTPUT WAS TOO LONG. YOU MUST OUTPUT LESS THAN {dynamic_max_length} CHARACTERS. CUT THE TEXT AGGRESSIVELY."
                else:
                    prompt += f" The text MUST be under {dynamic_max_length} characters. Count every character. Prioritize brevity."
                
                data["contents"][0]["parts"][0]["text"] = prompt
                
                response_data = self._post_generate_content(data)
                if ("candidates" in response_data and len(response_data["candidates"]) > 0):
                    translated_text = response_data["candidates"][0]["content"]["parts"][0]["text"]
            
            # If it's STILL too long after retries, truncate as a absolute last resort to prevent API crash
            if max_length and len(translated_text) > max_length:
                from utils import print_warning
                print_warning(f"  ⚠️  Translation still too long ({len(translated_text)} chars) after {max_retries} retries. Final truncation to {max_length}.")
                translated_text = translated_text[:max_length]
            
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
    
    _lock = threading.Lock()
    _request_times: List[float] = []

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
            "max_tokens": 4000, # Cap it at 4000 to prevent 21k responses
            "temperature": 0.1,
            "reasoning": {"enabled": True}
        }


    def translate(self, text: str, target_language: str, 
                  max_length: Optional[int] = None, 
                  is_keywords: bool = False,
                  seed: Optional[int] = None,
                  refinement: Optional[str] = None) -> str:
        """Translate using OpenRouter."""
        _ = seed

        # Log the request
        log_ai_request("OpenRouter", self.model, text, target_language, max_length, is_keywords)
        
        # Rate limiting: 50 RPM (Requests Per Minute)
        with OpenRouterProvider._lock:
            now = time.time()
            # Keep only timestamps from the last 60 seconds
            OpenRouterProvider._request_times = [t for t in OpenRouterProvider._request_times if now - t < 60]
            
            if len(OpenRouterProvider._request_times) >= 50:
                # Calculate how long to wait until the oldest request falls out of the window
                sleep_time = 60.0 - (now - OpenRouterProvider._request_times[0]) + 0.1
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
                # Update 'now' and clean up again after sleeping
                now = time.time()
                OpenRouterProvider._request_times = [t for t in OpenRouterProvider._request_times if now - t < 60]
            
            OpenRouterProvider._request_times.append(time.time())

        try:
            url = f"{self.base_url}/chat/completions"
            
            # OpenRouter requires specific headers for tracking
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/Persie0/translateR", # Recommended by OpenRouter
                "X-Title": "TranslateR App Store Tool"
            }
            
            # Build system message
            system_message = (
                f"You are a professional translator specializing in App Store metadata translation. "
                f"Translate the following text to {target_language}. "
                f"Maintain the marketing tone and style of the original text. "
                f"IMPORTANT: Output ONLY the translated text. Do not include any reasoning, "
                f"internal thinking tags (like <think>), or explanations."
            )
            
            if is_keywords:
                system_message += " For keywords, provide a comma-separated list and keep it concise."

            if refinement:
                system_message += f" Additional guidance: {refinement}"
            
            if max_length:
                system_message += (
                    f" CRITICAL: Your translation MUST be EXACTLY {max_length} characters or fewer "
                    f"INCLUDING ALL SPACES, PUNCTUATION, AND SPECIAL CHARACTERS. Count every single "
                    f"character including spaces between words. Do not add ellipsis (...) at the end. "
                    f"Create a concise but meaningful translation that captures the essence of the "
                    f"original message while staying within the character limit."
                )
            
            user_content = text
            if max_length:
                user_content = f"{text}\n\nREMINDER: Target language is {target_language}. Max {max_length} chars. ONLY return translation."
            
            data = self._build_request_payload(system_message, user_content)
            
            # --- Robust Inlined Parsing ---
            def parse_payload(payload: Dict[str, Any]) -> str:
                # 1. Check for top-level errors
                if "error" in payload:
                    err = payload["error"]
                    msg = err.get("message") if isinstance(err, dict) else str(err)
                    raise ValueError(f"OpenRouter Error: {msg}")

                # 2. Check for choices
                choices = payload.get("choices", [])
                if not choices:
                    raise ValueError(f"OpenRouter returned no choices. Keys: {list(payload.keys())}")

                # 3. Extract message content
                message = choices[0].get("message", {})
                content = message.get("content")
                
                if content is not None and str(content).strip():
                    content_str = str(content).strip()
                    # Strip <think> tags if present
                    import re
                    content_str = re.sub(r'<think>.*?</think>', '', content_str, flags=re.DOTALL).strip()
                    # Strip common reasoning prefixes if model ignored prompt
                    content_str = re.sub(r'^(Thinking|Reasoning|Analysis):.*?\n', '', content_str, flags=re.DOTALL | re.IGNORECASE).strip()
                    return content_str
                
                # 4. Check for reasoning (backup for some models)
                # NOTE: We generally DON'T want to return reasoning as translation
                # but if the model ONLY returned reasoning, we'll take it as a last resort
                reasoning = message.get("reasoning") or message.get("reasoning_details")
                if reasoning and str(reasoning).strip():
                    return str(reasoning).strip()[:max_length] if max_length else str(reasoning).strip()

                # 5. Check for refusal
                refusal = message.get("refusal")
                if refusal:
                    raise ValueError(f"OpenRouter Refusal: {refusal}")
                
                # 6. Check for text (legacy format)
                text_val = choices[0].get("text")
                if text_val:
                    return str(text_val).strip()

                raise ValueError(f"OpenRouter returned empty content. Message keys: {list(message.keys())}")
            # -------------------------------

            response = requests.post(url, headers=headers, json=data)
            if not response.ok:
                message = _extract_error_message(response)
                raise ValueError(f"OpenRouter API error ({response.status_code}): {message}")
            
            response_data = response.json()
            translated_text = parse_payload(response_data)
            
            # Check character limit and retry if needed (up to 8 times)
            retry_count = 0
            max_retries = 8
            
            while max_length and len(translated_text) > max_length and retry_count < max_retries:
                retry_count += 1
                # Decrease the effective max length by 5 for each retry to force more aggressive shortening
                dynamic_max_length = max(10, max_length - (retry_count * 5))
                log_character_limit_retry("OpenRouter", len(translated_text), max_length)
                
                # Try again with even stricter instructions
                if retry_count == max_retries:
                    system_message += f" FINAL WARNING: THE PREVIOUS OUTPUT WAS TOO LONG. YOU MUST OUTPUT LESS THAN {dynamic_max_length} CHARACTERS. CUT THE TEXT AGGRESSIVELY."
                else:
                    system_message += f" The text MUST be under {dynamic_max_length} characters. Count every character. Prioritize brevity."
                
                user_content = text
                if dynamic_max_length:
                    user_content = f"{text}\n\nREMINDER: Target language is {target_language}. Max {dynamic_max_length} chars. ONLY return translation."
                
                data = self._build_request_payload(system_message, user_content)
                
                response = requests.post(url, headers=headers, json=data)
                if not response.ok:
                    message = _extract_error_message(response)
                    raise ValueError(f"OpenRouter API error ({response.status_code}): {message}")
                
                response_data = response.json()
                translated_text = parse_payload(response_data)
            
            # If it's STILL too long after retries, truncate as a absolute last resort to prevent API crash
            if max_length and len(translated_text) > max_length:
                from utils import print_warning
                print_warning(f"  ⚠️  Translation still too long ({len(translated_text)} chars) after {max_retries} retries. Final truncation to {max_length}.")
                translated_text = translated_text[:max_length]
            
            # Log successful response
            log_ai_response("OpenRouter", translated_text, success=True)
            return translated_text.strip()
            
        except Exception as e:
            # Log error response
            log_ai_response("OpenRouter", "", success=False, error=str(e))
            raise Exception(f"OpenRouter translation failed: {str(e)}")
    
    def get_name(self) -> str:
        return "OpenRouter"


class NVIDIAProvider(AIProvider):
    """NVIDIA NIM AI provider."""
    
    def __init__(self, api_key: str, model: str = "mistralai/mistral-large-3-675b-instruct-2512"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://integrate.api.nvidia.com/v1"
        self._lock = threading.Lock()
    
    def _build_request_payload(self, system_message: str, text: str) -> Dict[str, Any]:
        """Build request payload for NVIDIA API (OpenAI compatible)."""
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": text}
            ],
            "max_tokens": 2048,
            "temperature": 0.7,
            "top_p": 1,
            "stream": False
        }
    
    def _extract_response_text(self, response_data: Dict[str, Any]) -> str:
        """Extract translated text from NVIDIA response."""
        if "choices" in response_data and len(response_data["choices"]) > 0:
            msg = response_data["choices"][0].get("message", {})
            content = msg.get("content")
            if content is not None:
                return str(content)
            
            # Check for refusal
            refusal = msg.get("refusal")
            if refusal:
                raise ValueError(f"NVIDIA Refusal: {refusal}")

            raise ValueError("NVIDIA returned empty content")
        raise ValueError("Unexpected NVIDIA API response format")
    
    def _post_with_retry(self, url: str, headers: Dict[str, str], data: Dict[str, Any]) -> requests.Response:
        """Post request to NVIDIA with exponential backoff for rate limits and server errors."""
        max_retries = 20
        with self._lock:
            for attempt in range(max_retries + 1):
                try:
                    response = requests.post(url, headers=headers, json=data)
                    # Retry on rate limit (429) or common server errors (5xx)
                    if response.status_code in [429, 500, 502, 503, 504] and attempt < max_retries:
                        sleep_time = 2
                        print(f"  [NVIDIA] API error ({response.status_code}). Retrying in {sleep_time}s... (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(sleep_time)
                        continue
                    return response
                except requests.exceptions.RequestException as e:
                    if attempt < max_retries:
                        sleep_time = 2
                        print(f"  [NVIDIA] Connection error. Retrying in {sleep_time}s... (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(sleep_time)
                        continue
                    raise e
            return requests.post(url, headers=headers, json=data) # Final attempt if loop finishes somehow

    def translate(self, text: str, target_language: str, 
                  max_length: Optional[int] = None, 
                  is_keywords: bool = False,
                  seed: Optional[int] = None,
                  refinement: Optional[str] = None) -> str:
        """Translate using NVIDIA NIM."""
        _ = seed

        # Log the request
        log_ai_request("NVIDIA", self.model, text, target_language, max_length, is_keywords)
        
        try:
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Build system message
            system_message = (
                f"You are a professional translator specializing in App Store metadata translation. "
                f"Translate the following text to {target_language}. "
                f"Maintain the marketing tone and style of the original text. "
                f"IMPORTANT: Your response MUST contain ONLY the translated text. "
                f"Do not include preambles, explanations, original text, or any conversational filler."
            )
            
            if is_keywords:
                system_message = (
                    f"You are an App Store SEO expert. Translate these keywords to {target_language}. "
                    f"Output ONLY a comma-separated list of the translated keywords. "
                    f"Do not include any other text, headers, or explanations."
                )
            
            if refinement:
                system_message += f" Additional guidance: {refinement}"
            
            if max_length:
                system_message += (
                    f" CRITICAL: Your translation MUST be {max_length} characters or fewer. "
                    f"Count every character including spaces. This is a strict technical limit."
                )
            
            user_content = text
            if max_length:
                user_content = f"{text}\n\nREMINDER: Target language is {target_language}. Max {max_length} chars. ONLY return translation."
            
            data = self._build_request_payload(system_message, user_content)
            
            response = self._post_with_retry(url, headers, data)
            if not response.ok:
                message = _extract_error_message(response)
                raise ValueError(f"NVIDIA API error ({response.status_code}): {message}")
            
            response_data = response.json()
            translated_text = self._extract_response_text(response_data)
            
            # Check character limit and retry if needed (up to 8 times)
            retry_count = 0
            max_retries = 8
            
            while max_length and len(translated_text) > max_length and retry_count < max_retries:
                retry_count += 1
                # Decrease the effective max length by 5 for each retry to force more aggressive shortening
                dynamic_max_length = max(10, max_length - (retry_count * 5))
                log_character_limit_retry("NVIDIA", len(translated_text), max_length)
                
                # Try again with even stricter instructions
                if retry_count == max_retries:
                    system_message += f" FINAL WARNING: THE PREVIOUS OUTPUT WAS TOO LONG. YOU MUST OUTPUT LESS THAN {dynamic_max_length} CHARACTERS. CUT THE TEXT AGGRESSIVELY."
                else:
                    system_message += f" The text MUST be under {dynamic_max_length} characters. Count every character. Prioritize brevity."
                
                user_content = text
                if dynamic_max_length:
                    user_content = f"{text}\n\nREMINDER: Target language is {target_language}. Max {dynamic_max_length} chars. ONLY return translation."
                
                data = self._build_request_payload(system_message, user_content)
                
                response = self._post_with_retry(url, headers, data)
                if not response.ok:
                    message = _extract_error_message(response)
                    raise ValueError(f"NVIDIA API error ({response.status_code}): {message}")
                
                response_data = response.json()
                translated_text = self._extract_response_text(response_data)
            
            # If it's STILL too long after retries, truncate as a absolute last resort to prevent API crash
            if max_length and len(translated_text) > max_length:
                from utils import print_warning
                print_warning(f"  ⚠️  Translation still too long ({len(translated_text)} chars) after {max_retries} retries. Final truncation to {max_length}.")
                translated_text = translated_text[:max_length]
            
            # Log successful response
            log_ai_response("NVIDIA", translated_text, success=True)
            return translated_text.strip()
            
        except Exception as e:
            # Log error response
            log_ai_response("NVIDIA", "", success=False, error=str(e))
            raise Exception(f"NVIDIA translation failed: {str(e)}")
    
    def get_name(self) -> str:
        return "NVIDIA"


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
