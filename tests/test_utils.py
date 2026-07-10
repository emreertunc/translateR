import unittest

from utils import detect_base_language


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


if __name__ == "__main__":
    unittest.main()
