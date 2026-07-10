import unittest
from unittest.mock import Mock

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


if __name__ == "__main__":
    unittest.main()
