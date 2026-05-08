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

if __name__ == "__main__":
    unittest.main()
