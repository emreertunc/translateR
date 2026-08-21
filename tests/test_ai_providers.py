import unittest
from unittest.mock import Mock, patch

from ai_providers import (
    OPENAI_RETRYABLE_STATUS_CODES,
    GoogleGeminiProvider,
    OpenAIProvider,
)


class OpenAIProviderTests(unittest.TestCase):
    @patch("ai_providers.log_ai_response")
    @patch("ai_providers.log_ai_request")
    @patch("ai_providers.request_with_retries")
    def test_translate_uses_responses_api_with_stable_reasoning_defaults(
        self,
        request_mock,
        _request_log_mock,
        _response_log_mock,
    ):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "status": "completed",
            "output": [
                {"type": "reasoning", "summary": []},
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Hallo",
                            "annotations": [],
                        }
                    ],
                },
            ],
        }
        request_mock.return_value = response

        for model in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"):
            with self.subTest(model=model):
                request_mock.reset_mock()
                provider = OpenAIProvider("test-key", model)

                translated = provider.translate("Hello", "German")

                self.assertEqual(translated, "Hallo")
                request_mock.assert_called_once()
                self.assertEqual(
                    request_mock.call_args.args[:2],
                    ("POST", "https://api.openai.com/v1/responses"),
                )
                payload = request_mock.call_args.kwargs["json"]
                self.assertEqual(payload["model"], model)
                self.assertEqual(payload["max_output_tokens"], 25_000)
                self.assertEqual(payload["reasoning"], {"effort": "medium"})
                self.assertIs(payload["store"], False)
                self.assertEqual(
                    request_mock.call_args.kwargs["retry_status_codes"],
                    OPENAI_RETRYABLE_STATUS_CODES,
                )
                self.assertNotIn("retry_post", request_mock.call_args.kwargs)
                self.assertNotIn("temperature", payload)
                self.assertNotIn("text", payload)

    def test_incomplete_response_is_not_returned_as_translation(self):
        provider = OpenAIProvider("test-key", "gpt-5.6-sol")

        with self.assertRaisesRegex(ValueError, "max_output_tokens"):
            provider._extract_response_text(
                {
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                    "output_text": "Partial translation",
                }
            )

    def test_failed_response_uses_error_code_when_message_is_missing(self):
        provider = OpenAIProvider("test-key", "gpt-5.6-sol")

        with self.assertRaisesRegex(ValueError, "rate_limit"):
            provider._extract_response_text(
                {
                    "status": "failed",
                    "error": {"code": "rate_limit"},
                }
            )

    @patch("ai_providers.log_ai_response")
    @patch("ai_providers.log_ai_request")
    @patch("ai_providers.request_with_retries")
    def test_http_error_surfaces_openai_error_message(
        self,
        request_mock,
        _request_log_mock,
        _response_log_mock,
    ):
        response = Mock()
        response.ok = False
        response.status_code = 400
        response.json.return_value = {
            "error": {"message": "Unsupported model setting"}
        }
        response.text = ""
        request_mock.return_value = response
        provider = OpenAIProvider("test-key", "gpt-5.6-sol")

        with self.assertRaisesRegex(Exception, "Unsupported model setting"):
            provider.translate("Hello", "German")

    @patch("ai_providers.log_character_limit_retry")
    @patch("ai_providers.log_ai_response")
    @patch("ai_providers.log_ai_request")
    @patch("ai_providers.request_with_retries")
    def test_length_retry_surfaces_openai_error_message(
        self,
        request_mock,
        _request_log_mock,
        _response_log_mock,
        _length_log_mock,
    ):
        completed_response = Mock()
        completed_response.ok = True
        completed_response.json.return_value = {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "Too long"}
                    ],
                }
            ],
        }
        error_response = Mock()
        error_response.ok = False
        error_response.status_code = 400
        error_response.json.return_value = {
            "error": {"message": "Retry request rejected"}
        }
        error_response.text = ""
        request_mock.side_effect = [completed_response, error_response]
        provider = OpenAIProvider("test-key", "gpt-5.6-sol")

        with self.assertRaisesRegex(Exception, "Retry request rejected"):
            provider.translate("Hello", "German", max_length=3)


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
