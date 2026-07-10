import unittest

from utils import detect_base_language, get_field_limit


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
