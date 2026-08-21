import unittest

from utils import (
    APP_STORE_LOCALES,
    canonicalize_app_store_locale,
    detect_base_language,
    get_field_limit,
    locales_equivalent,
)


OFFICIAL_APP_STORE_LOCALE_CODES = {
    "ar-SA",
    "bn-BD",
    "ca",
    "zh-Hans",
    "zh-Hant",
    "hr",
    "cs",
    "da",
    "nl-NL",
    "en-AU",
    "en-CA",
    "en-GB",
    "en-US",
    "fi",
    "fr-FR",
    "fr-CA",
    "de-DE",
    "el",
    "gu-IN",
    "he",
    "hi",
    "hu",
    "id",
    "it",
    "ja",
    "kn-IN",
    "ko",
    "ms",
    "ml-IN",
    "mr-IN",
    "no",
    "or-IN",
    "pl",
    "pt-BR",
    "pt-PT",
    "pa-IN",
    "ro",
    "ru",
    "sk",
    "sl-SI",
    "es-MX",
    "es-ES",
    "sv",
    "ta-IN",
    "te-IN",
    "th",
    "tr",
    "uk",
    "ur-PK",
    "vi",
}


class AppStoreLocaleTests(unittest.TestCase):
    def test_catalog_matches_official_apple_metadata_locale_codes(self):
        self.assertEqual(len(APP_STORE_LOCALES), 50)
        self.assertEqual(set(APP_STORE_LOCALES), OFFICIAL_APP_STORE_LOCALE_CODES)

    def test_legacy_aliases_resolve_to_canonical_apple_codes(self):
        aliases = {
            "bn-IN": "bn-BD",
            "gu": "gu-IN",
            "hi-IN": "hi",
            "kn": "kn-IN",
            "ml": "ml-IN",
            "mr": "mr-IN",
            "or": "or-IN",
            "pa": "pa-IN",
            "sl": "sl-SI",
            "ta": "ta-IN",
            "te": "te-IN",
            "ur": "ur-PK",
        }

        for legacy_code, expected in aliases.items():
            with self.subTest(legacy_code=legacy_code):
                self.assertEqual(
                    canonicalize_app_store_locale(legacy_code),
                    expected,
                )

    def test_canonicalization_accepts_case_and_underscore_variants(self):
        variants = {
            " HI_in ": "hi",
            "EN_us": "en-US",
            "fr_ca": "fr-CA",
            "GU_in": "gu-IN",
            "zh_hANS": "zh-Hans",
            "ZH_hANT": "zh-Hant",
        }

        for input_code, expected in variants.items():
            with self.subTest(input_code=input_code):
                self.assertEqual(
                    canonicalize_app_store_locale(input_code),
                    expected,
                )

    def test_unsupported_locale_has_no_canonical_code(self):
        self.assertIsNone(canonicalize_app_store_locale("as"))
        self.assertIsNone(canonicalize_app_store_locale("zh"))
        self.assertIsNone(canonicalize_app_store_locale(""))
        self.assertIsNone(canonicalize_app_store_locale(None))

    def test_chinese_script_locales_remain_distinct(self):
        self.assertFalse(locales_equivalent("zh-Hans", "zh-Hant"))
        self.assertFalse(locales_equivalent("zh", "zh-Hans"))



class BaseLanguageDetectionTests(unittest.TestCase):
    def setUp(self):
        self.localizations = [
            {"attributes": {"locale": "en-US"}},
            {"attributes": {"locale": "tr"}},
            {"attributes": {"locale": "ar-SA"}},
        ]

    def test_primary_locale_takes_priority_over_english(self):
        self.assertEqual(
            detect_base_language(self.localizations, primary_locale="tr"),
            "tr",
        )

    def test_primary_base_locale_matches_regional_locale(self):
        self.assertEqual(
            detect_base_language(self.localizations, primary_locale="ar"),
            "ar-SA",
        )

    def test_missing_primary_locale_falls_back_to_english(self):
        self.assertEqual(
            detect_base_language(self.localizations, primary_locale="fr-FR"),
            "en-US",
        )


class FieldLimitTests(unittest.TestCase):
    def test_update_field_names_preserve_underscore_limits(self):
        self.assertEqual(get_field_limit("promotional_text"), 170)
        self.assertEqual(get_field_limit("whats_new"), 4000)


if __name__ == "__main__":
    unittest.main()
