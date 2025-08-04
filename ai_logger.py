"""
AI Logger System

Logs all AI provider requests and responses in human-readable format.
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


class AILogger:
    """Logs AI provider requests and responses."""
    
    def __init__(self, log_dir: str = "logs"):
        """
        Initialize AI logger.
        
        Args:
            log_dir: Directory to store log files
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True, mode=0o755)
        
        # Create log file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"ai_requests_{timestamp}.log"
        
        # Write header
        self._write_header()
    
    def _write_header(self):
        """Write log file header."""
        header = f"""
===============================================================================
TranslateR AI Request Log
Started: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
===============================================================================

"""
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write(header)
    
    def log_request(self, provider: str, model: str, text: str, 
                   target_language: str, max_length: Optional[int] = None,
                   is_keywords: bool = False):
        """
        Log AI translation request.
        
        Args:
            provider: AI provider name
            model: Model used
            text: Text being translated
            target_language: Target language
            max_length: Character limit
            is_keywords: Whether text is keywords
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        log_entry = f"""
[{timestamp}] REQUEST
Provider: {provider}
Model: {model}
Target Language: {target_language}
Max Length: {max_length if max_length else "No limit"}
Is Keywords: {is_keywords}
Original Text ({len(text)} chars):
{'-' * 50}
{text}
{'-' * 50}

"""
        
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)
    
    def log_response(self, provider: str, translated_text: str, 
                    success: bool = True, error: Optional[str] = None):
        """
        Log AI translation response.
        
        Args:
            provider: AI provider name
            translated_text: Translated text (if successful)
            success: Whether request was successful
            error: Error message (if failed)
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if success:
            log_entry = f"""[{timestamp}] RESPONSE - SUCCESS
Provider: {provider}
Translated Text ({len(translated_text)} chars):
{'-' * 50}
{translated_text}
{'-' * 50}

"""
        else:
            log_entry = f"""[{timestamp}] RESPONSE - ERROR
Provider: {provider}
Error:
{'-' * 50}
{error}
{'-' * 50}

"""
        
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)
    
    def log_character_limit_retry(self, provider: str, original_length: int, 
                                 max_length: int):
        """
        Log character limit retry attempt.
        
        Args:
            provider: AI provider name
            original_length: Length of first translation
            max_length: Required maximum length
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        log_entry = f"""[{timestamp}] CHARACTER LIMIT RETRY
Provider: {provider}
Original translation: {original_length} chars
Required limit: {max_length} chars
Retrying with stricter instructions...

"""
        
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)
    
    def get_log_file_path(self) -> str:
        """Get the current log file path."""
        return str(self.log_file)


# Global logger instance
_logger_instance: Optional[AILogger] = None


def get_ai_logger() -> AILogger:
    """Get or create global AI logger instance."""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = AILogger()
    return _logger_instance


def log_ai_request(provider: str, model: str, text: str, 
                  target_language: str, max_length: Optional[int] = None,
                  is_keywords: bool = False):
    """Convenience function to log AI request."""
    logger = get_ai_logger()
    logger.log_request(provider, model, text, target_language, max_length, is_keywords)


def log_ai_response(provider: str, translated_text: str = "", 
                   success: bool = True, error: Optional[str] = None):
    """Convenience function to log AI response."""
    logger = get_ai_logger()
    logger.log_response(provider, translated_text, success, error)


def log_character_limit_retry(provider: str, original_length: int, max_length: int):
    """Convenience function to log character limit retry."""
    logger = get_ai_logger()
    logger.log_character_limit_retry(provider, original_length, max_length)