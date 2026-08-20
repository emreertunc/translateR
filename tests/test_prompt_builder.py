import tempfile
import unittest
from pathlib import Path

from config import ConfigManager
from prompt_builder import build_translation_prompt


class PromptBuilderTests(unittest.TestCase):
    def test_builds_runtime_keyword_and_limit_rules(self):
        prompt = build_translation_prompt(
            "# Base\nKeep translations natural.",
            "German",
            max_length=100,
            is_keywords=True,
            refinement="Keep brand names unchanged.",
        )

        self.assertIn("Keep translations natural.", prompt)
        self.assertIn("Translate the provided App Store metadata text to German.", prompt)
        self.assertIn("Return only the translated text.", prompt)
        self.assertIn("comma-separated keyword list", prompt)
        self.assertIn("MUST be EXACTLY 100 characters or fewer", prompt)
        self.assertIn("INCLUDE ALL SPACES, PUNCTUATION, AND SPECIAL CHARACTERS", prompt)
        self.assertIn("Keep brand names unchanged.", prompt)
        self.assertLess(
            prompt.index("Keep brand names unchanged."),
            prompt.index("Keep translations natural."),
        )
        self.assertIn("override the static translation instructions", prompt)

    def test_retry_prompt_adds_stricter_limit_rule(self):
        prompt = build_translation_prompt(
            "# Base",
            "French",
            max_length=30,
            retry_for_length=True,
        )

        self.assertIn("previous translation exceeded the limit", prompt)
        self.assertIn("MUST be under 30 characters INCLUDING SPACES AND PUNCTUATION", prompt)


class ConfigManagerInstructionTests(unittest.TestCase):
    def test_uses_markdown_instructions_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ConfigManager(tmp)

            self.assertEqual(manager.instructions_file.name, "instructions.md")
            self.assertTrue((Path(tmp) / "instructions.md").exists())
            self.assertIn("App Store Metadata", manager.load_instructions())

    def test_uses_selected_google_models_and_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ConfigManager(tmp)

            self.assertEqual(
                manager.list_provider_models("google"),
                [
                    "gemini-3.7-flash",
                    "gemini-3.5-flash-lite",
                    "gemini-3.1-pro-preview",
                ],
            )
            self.assertEqual(manager.get_default_model("google"), "gemini-3.7-flash")

    def test_migrates_removed_google_model_without_changing_other_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ConfigManager(tmp)
            providers = manager.load_providers()
            providers["google"]["models"] = ["gemini-3-flash-preview"]
            providers["google"]["default_model"] = "gemini-3-flash-preview"
            providers["custom_setting"] = {"preserve": True}
            manager.save_providers(providers)

            migrated = ConfigManager(tmp).load_providers()

            self.assertEqual(
                migrated["google"]["models"],
                [
                    "gemini-3.7-flash",
                    "gemini-3.5-flash-lite",
                    "gemini-3.1-pro-preview",
                ],
            )
            self.assertEqual(migrated["google"]["default_model"], "gemini-3.7-flash")
            self.assertEqual(migrated["custom_setting"], {"preserve": True})

    def test_migration_preserves_supported_google_model_choice(self):
        for selected_model in ("gemini-3.5-flash-lite", "gemini-3.1-pro-preview"):
            with self.subTest(selected_model=selected_model):
                with tempfile.TemporaryDirectory() as tmp:
                    manager = ConfigManager(tmp)
                    providers = manager.load_providers()
                    providers["google"]["models"] = [selected_model]
                    providers["google"]["default_model"] = selected_model
                    manager.save_providers(providers)

                    migrated = ConfigManager(tmp).load_providers()

                    self.assertEqual(migrated["google"]["default_model"], selected_model)

    def test_migration_does_not_overwrite_malformed_provider_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            providers_file = Path(tmp) / "providers.json"
            malformed_config = "{not-json"
            providers_file.write_text(malformed_config)

            ConfigManager(tmp)

            self.assertEqual(providers_file.read_text(), malformed_config)

    def test_migration_ignores_non_object_provider_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            providers_file = Path(tmp) / "providers.json"
            providers_file.write_text("[]")

            ConfigManager(tmp)

            self.assertEqual(providers_file.read_text(), "[]")

if __name__ == "__main__":
    unittest.main()
