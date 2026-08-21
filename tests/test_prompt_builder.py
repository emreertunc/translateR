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

    def test_uses_selected_openai_models_and_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ConfigManager(tmp)

            self.assertEqual(
                manager.list_provider_models("openai"),
                ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"],
            )
            self.assertEqual(manager.get_default_model("openai"), "gpt-5.6-sol")

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

    def test_migrates_openai_models_without_changing_cost_tier(self):
        replacements = (
            ("gpt-5.5", "gpt-5.6-sol"),
            ("gpt-5.4", "gpt-5.6-sol"),
            ("gpt-5.2", "gpt-5.6-sol"),
            ("gpt-5.4-mini", "gpt-5.6-terra"),
            ("gpt-5.4-mini-2026-03-17", "gpt-5.6-terra"),
            ("gpt-5-mini-2025-08-07", "gpt-5.6-terra"),
            ("gpt-5.4-nano", "gpt-5.6-luna"),
            ("gpt-5.4-nano-2026-03-17", "gpt-5.6-luna"),
            ("gpt-5-nano-2025-08-07", "gpt-5.6-luna"),
        )
        for selected_model, expected_model in replacements:
            with self.subTest(selected_model=selected_model):
                with tempfile.TemporaryDirectory() as tmp:
                    manager = ConfigManager(tmp)
                    providers = manager.load_providers()
                    providers["openai"]["models"] = [selected_model]
                    providers["openai"]["default_model"] = selected_model
                    providers["openai"]["custom_setting"] = "preserve"
                    manager.save_providers(providers)

                    migrated = ConfigManager(tmp).load_providers()

                    self.assertEqual(
                        migrated["openai"]["models"],
                        ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"],
                    )
                    self.assertEqual(
                        migrated["openai"]["default_model"],
                        expected_model,
                    )
                    self.assertEqual(
                        migrated["openai"]["custom_setting"],
                        "preserve",
                    )

    def test_migration_preserves_unknown_custom_model_choices(self):
        custom_models = {
            "google": (
                "gemini-custom-list-model",
                "gemini-custom-default-model",
            ),
            "openai": (
                "gpt-custom-list-model",
                "gpt-custom-default-model",
            ),
        }
        for provider_name, (listed_model, selected_model) in custom_models.items():
            with self.subTest(provider_name=provider_name):
                with tempfile.TemporaryDirectory() as tmp:
                    manager = ConfigManager(tmp)
                    providers = manager.load_providers()
                    providers[provider_name]["models"] = [
                        "",
                        f"  {listed_model}  ",
                        listed_model,
                    ]
                    providers[provider_name]["default_model"] = selected_model
                    manager.save_providers(providers)

                    migrated = ConfigManager(tmp).load_providers()

                    self.assertIn(listed_model, migrated[provider_name]["models"])
                    self.assertEqual(
                        migrated[provider_name]["models"].count(listed_model),
                        1,
                    )
                    self.assertIn(selected_model, migrated[provider_name]["models"])
                    self.assertEqual(
                        migrated[provider_name]["default_model"],
                        selected_model,
                    )
                    self.assertEqual(
                        ConfigManager(tmp).load_providers(),
                        migrated,
                    )

    def test_migration_preserves_supported_openai_model_choice(self):
        for selected_model in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"):
            with self.subTest(selected_model=selected_model):
                with tempfile.TemporaryDirectory() as tmp:
                    manager = ConfigManager(tmp)
                    providers = manager.load_providers()
                    providers["openai"]["models"] = [selected_model]
                    providers["openai"]["default_model"] = selected_model
                    manager.save_providers(providers)

                    migrated = ConfigManager(tmp).load_providers()

                    self.assertEqual(migrated["openai"]["default_model"], selected_model)

    def test_migration_replaces_non_string_openai_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ConfigManager(tmp)
            providers = manager.load_providers()
            providers["openai"]["default_model"] = []
            manager.save_providers(providers)

            migrated = ConfigManager(tmp).load_providers()

            self.assertEqual(migrated["openai"]["default_model"], "gpt-5.6-sol")

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
