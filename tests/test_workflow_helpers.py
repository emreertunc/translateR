import io
import unittest
from unittest.mock import patch

from workflows.helpers import (
    choose_target_locales,
    combine_prompt_refinements,
    confirm_locale_write,
    display_locale_table,
    prompt_translation_guidance,
)


class WorkflowHelperTests(unittest.TestCase):
    def test_display_locale_table_prints_all_locales(self):
        locales = {f"l-{index}": f"Language {index}" for index in range(1, 24)}
        output = io.StringIO()

        with patch("sys.stdout", output):
            display_locale_table(locales)

        rendered = output.getvalue()
        self.assertIn("l-1", rendered)
        self.assertIn("Language 23", rendered)
        self.assertNotIn("more", rendered)

    def test_combine_prompt_refinements_prioritizes_user_guidance(self):
        combined = combine_prompt_refinements(
            "Do not translate WidgetPro.",
            "Keep tone concise.",
        )

        self.assertLess(
            combined.index("Do not translate WidgetPro."),
            combined.index("Keep tone concise."),
        )
        self.assertIn("override the static translation instructions", combined)

    def test_prompt_translation_guidance_asks_for_text_when_enabled(self):
        prompts = []

        def fake_input(prompt):
            prompts.append(prompt)
            return "y" if len(prompts) == 1 else "Keep AI untranslated."

        with patch("builtins.input", fake_input):
            combined = prompt_translation_guidance("Keep tone concise.")

        self.assertEqual(len(prompts), 2)
        self.assertIn("Keep AI untranslated.", combined)
        self.assertLess(
            combined.index("Keep AI untranslated."),
            combined.index("Keep tone concise."),
        )

    def test_prompt_translation_guidance_keeps_global_when_disabled(self):
        with patch("builtins.input", lambda prompt: "n"):
            combined = prompt_translation_guidance("Keep tone concise.")

        self.assertEqual(combined, "Keep tone concise.")

    def test_choose_target_locales_blank_cancels(self):
        with patch("builtins.input", lambda prompt: ""):
            selected = choose_target_locales(
                {"de-DE": "German", "fr-FR": "French"},
                "en-US",
                preferred_locales={"de-DE"},
            )

        self.assertEqual(selected, [])

    def test_choose_target_locales_invalid_cancels(self):
        with patch("builtins.input", lambda prompt: "de-DE,invalid"):
            selected = choose_target_locales(
                {"de-DE": "German", "fr-FR": "French"},
                "en-US",
            )

        self.assertEqual(selected, [])

    def test_choose_target_locales_all_is_explicit(self):
        with patch("builtins.input", lambda prompt: "all"):
            selected = choose_target_locales(
                {"de-DE": "German", "fr-FR": "French"},
                "en-US",
            )

        self.assertEqual(selected, ["de-DE", "fr-FR"])

    def test_confirm_locale_write_requires_yes(self):
        with patch("builtins.input", lambda prompt: "n"):
            self.assertFalse(confirm_locale_write("Translation", ["de-DE"]))

        with patch("builtins.input", lambda prompt: "yes"):
            self.assertTrue(confirm_locale_write("Translation", ["de-DE"]))


if __name__ == "__main__":
    unittest.main()
