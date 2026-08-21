import unittest
from unittest.mock import Mock, patch

import requests

from http_client import DEFAULT_TIMEOUT, request_with_retries


def make_response(status_code, headers=None):
    response = Mock(spec=requests.Response)
    response.status_code = status_code
    response.headers = headers or {}
    return response


class HttpRetryTests(unittest.TestCase):
    @patch("http_client.time.sleep")
    @patch("http_client.requests.request")
    def test_rate_limit_retries_post_with_retry_after(self, request_mock, sleep_mock):
        request_mock.side_effect = [
            make_response(429, {"Retry-After": "0"}),
            make_response(200),
        ]

        response = request_with_retries("POST", "https://example.com", max_retries=2)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(request_mock.call_count, 2)
        sleep_mock.assert_called_once_with(0.0)

    @patch("http_client.requests.request")
    def test_post_server_error_is_not_retried_by_default(self, request_mock):
        request_mock.return_value = make_response(503)

        response = request_with_retries("POST", "https://example.com", max_retries=2)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(request_mock.call_count, 1)

    @patch("http_client.time.sleep")
    @patch("http_client.requests.request")
    def test_provider_post_retries_server_error_when_enabled(self, request_mock, sleep_mock):
        request_mock.side_effect = [make_response(503), make_response(200)]

        response = request_with_retries(
            "POST",
            "https://example.com",
            max_retries=2,
            retry_post=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(request_mock.call_count, 2)
        sleep_mock.assert_called_once()

    @patch("http_client.time.sleep")
    @patch("http_client.requests.request")
    def test_post_retries_explicit_server_error_without_transport_retry(
        self,
        request_mock,
        sleep_mock,
    ):
        request_mock.side_effect = [make_response(503), make_response(200)]

        response = request_with_retries(
            "POST",
            "https://example.com",
            max_retries=2,
            retry_status_codes={408, 429, 500, 502, 503, 504},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(request_mock.call_count, 2)
        sleep_mock.assert_called_once()

    @patch("http_client.requests.request")
    def test_post_transport_error_is_not_retried_by_status_policy(self, request_mock):
        for error in (
            requests.exceptions.ReadTimeout("timed out"),
            requests.exceptions.ConnectionError("disconnected"),
        ):
            with self.subTest(error=type(error).__name__):
                request_mock.reset_mock()
                request_mock.side_effect = error

                with self.assertRaises(type(error)):
                    request_with_retries(
                        "POST",
                        "https://example.com",
                        max_retries=2,
                        retry_status_codes={408, 429, 500, 502, 503, 504},
                    )

                self.assertEqual(request_mock.call_count, 1)

    @patch("http_client.requests.request")
    def test_requests_have_explicit_timeout(self, request_mock):
        request_mock.return_value = make_response(200)

        request_with_retries("GET", "https://example.com")

        self.assertEqual(request_mock.call_args.kwargs["timeout"], DEFAULT_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
