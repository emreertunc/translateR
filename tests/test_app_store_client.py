import unittest
from unittest.mock import Mock, patch

import requests

from app_store_client import AppStoreConnectClient


class AppStoreLocalizationPayloadTests(unittest.TestCase):
    def setUp(self):
        self.client = AppStoreConnectClient("key", "issuer", "private-key")

    def test_version_localization_create_owns_marketing_and_support_urls(self):
        self.client._request = Mock(return_value={})

        self.client.create_app_store_version_localization(
            version_id="version-id",
            locale="de-DE",
            description="Beschreibung",
            marketing_url="https://example.com/marketing",
            support_url="https://example.com/support",
        )

        payload = self.client._request.call_args.kwargs["data"]
        attributes = payload["data"]["attributes"]
        self.assertEqual(attributes["marketingUrl"], "https://example.com/marketing")
        self.assertEqual(attributes["supportUrl"], "https://example.com/support")

    def test_version_localization_update_owns_marketing_and_support_urls(self):
        self.client._request = Mock(side_effect=[
            {"data": {"attributes": {}}},
            {"data": {"attributes": {}}},
        ])

        self.client.update_app_store_version_localization(
            localization_id="localization-id",
            marketing_url="https://example.com/marketing",
            support_url="https://example.com/support",
        )

        payload = self.client._request.call_args_list[1].kwargs["data"]
        attributes = payload["data"]["attributes"]
        self.assertEqual(attributes["marketingUrl"], "https://example.com/marketing")
        self.assertEqual(attributes["supportUrl"], "https://example.com/support")

    def test_app_info_localization_contains_only_app_info_urls(self):
        self.client._request = Mock(return_value={})

        self.client.create_app_info_localization(
            app_info_id="app-info-id",
            locale="de-DE",
            name="Name",
            subtitle="Subtitle",
            privacy_policy_url="https://example.com/privacy",
        )

        payload = self.client._request.call_args.kwargs["data"]
        attributes = payload["data"]["attributes"]
        self.assertEqual(attributes["privacyPolicyUrl"], "https://example.com/privacy")
        self.assertNotIn("marketingUrl", attributes)
        self.assertNotIn("supportUrl", attributes)

    def test_copy_localization_preserves_version_urls(self):
        source = {
            "data": [{
                "id": "source-localization",
                "attributes": {
                    "locale": "de-DE",
                    "description": "Beschreibung",
                    "marketingUrl": "https://example.com/marketing",
                    "supportUrl": "https://example.com/support",
                },
            }],
        }
        self.client.get_app_store_version_localizations = Mock(side_effect=[source, {"data": []}])
        self.client.create_app_store_version_localization = Mock(return_value={})

        result = self.client.copy_localization_from_previous_version(
            "source-version",
            "target-version",
            "de-DE",
        )

        self.assertTrue(result)
        call = self.client.create_app_store_version_localization.call_args
        self.assertEqual(call.kwargs["marketing_url"], "https://example.com/marketing")
        self.assertEqual(call.kwargs["support_url"], "https://example.com/support")

    def test_failed_patch_is_not_sent_twice(self):
        self.client.get_app_store_version_localization = Mock(
            return_value={"data": {"attributes": {}}}
        )
        self.client._request = Mock(side_effect=requests.exceptions.HTTPError("failed"))

        with self.assertRaises(requests.exceptions.HTTPError):
            self.client.update_app_store_version_localization(
                "localization-id",
                description="Updated description",
            )

        self.assertEqual(self.client._request.call_count, 1)


class AppStorePaginationTests(unittest.TestCase):
    def setUp(self):
        self.client = AppStoreConnectClient("key", "issuer", "private-key")
        self.client._generate_token = Mock(return_value="token")

    @staticmethod
    def make_response(payload):
        response = Mock(spec=requests.Response)
        response.status_code = 200
        response.content = b"{}"
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        return response

    @patch("app_store_client.request_with_retries")
    def test_get_requests_follow_and_merge_next_links(self, request_mock):
        request_mock.side_effect = [
            self.make_response({
                "data": [{"id": "1"}],
                "links": {"next": "https://api.appstoreconnect.apple.com/v1/apps?cursor=next"},
            }),
            self.make_response({
                "data": [{"id": "2"}],
                "links": {"next": None},
            }),
        ]

        result = self.client._request("GET", "apps")

        self.assertEqual([item["id"] for item in result["data"]], ["1", "2"])
        self.assertEqual(request_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
