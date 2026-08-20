import unittest
from unittest.mock import Mock, patch

from ai_providers import GoogleGeminiProvider


class GoogleGeminiProviderTests(unittest.TestCase):
    @patch("ai_providers.log_ai_response")
    @patch("ai_providers.log_ai_request")
    @patch("ai_providers.request_with_retries")
    def test_translate_uses_model_native_generation_defaults(
        self,
        request_mock,
        _request_log_mock,
        _response_log_mock,
    ):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Hallo"}]}}]
        }
        request_mock.return_value = response
        for model in (
            "gemini-3.7-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-pro-preview",
        ):
            with self.subTest(model=model):
                provider = GoogleGeminiProvider("test-key", model)

                translated = provider.translate("Hello", "German")

                self.assertEqual(translated, "Hallo")
                payload = request_mock.call_args.kwargs["json"]
                generation_config = payload["generationConfig"]
                self.assertEqual(generation_config, {"maxOutputTokens": 8000})


if __name__ == "__main__":
    unittest.main()
